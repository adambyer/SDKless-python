import urllib
import json
import tempfile
import os
import copy
#
from utilities import Utilities
from configuration import Configuration
from authentication import Authentication
from request import Request

class SDKless(object):

	MERGE_OPEN = '*|'
	MERGE_CLOSE = '|*'

	def __init__(self, api_name = None, global_vars = {}):
		self.config = None
		self.api_name = None
		self.uri = None
		self.global_vars = {}
		self.endpoint_vars = {}
		self.local_vars = {}

		self._prerequisites_complete = False
		self._auth = None
		self._time_limit = None

		if not api_name:
			return
		
		dir_path = os.path.dirname(os.path.realpath(__file__))

		with open("{}/config/{}.json".format(dir_path, api_name)) as f:
			config_content = f.read()

		try:
			with open("{}/config-custom/{}.custom.json".format(dir_path, api_name)) as f:
				custom_config_content = f.read()
		except:
			custom_config_content = None

		self.api_name = api_name
		self.global_vars = copy.deepcopy(global_vars)
		self.config = Configuration(self.MERGE_OPEN, self.MERGE_CLOSE)
		self.config.json = config_content
		self.config.json_custom = custom_config_content
		self.config.setup()

		# order of precedence
		# - any applied merge vars will negate subsequent merge vars
		# -- ex. an endpoint merge var will not apply if already applied by global vars
		# - set vars can be overwritten
		# -- ex. an endpoint set var will overwrite the same one done by global vars
		
		self.config.apply_custom_global_vars()
		self.config.apply_global_vars(self.global_vars)

		self._auth = Authentication(self.config)
		self.request = Request(self.config)

	# params are any parameters coming back as a result of the previous step
	def authenticate(self, step_id, params = {}):
		params = dict(params) # deal with immutable QueryDict

		# a step_id of -1 indicates a redirect step
		# find the next id after the redirect step
		if step_id == -1:
			step_id = self.config.get_authentication_redirect_step_id()

			if step_id is not None:
				step_id += 1

		# if params contains lists, only take 1st item
		# this happens when the previous step was an api call returning a query string that when parsed with parse_qs becomes a dict with list values
		# - like {u'oauth_token_secret': [u'abcdef'], u'oauth_token': [u'xyz123']}
		# - we want {u'oauth_token_secret': u'abcdef', u'oauth_token': u'xyz123'}
		for key, value in params.items():
			if isinstance(value, list):
				value = value[0]
			params[key] = value

		try:
			steps = self.config.settings['authentication']['steps']
		except:
			raise Exception('authentication steps not defined')

		if step_id >= (len(self.config.settings['authentication']['steps'])):
			return {'params': params, 'step_id': step_id, 'done': True}

		step = self.config.settings['authentication']['steps'][step_id]
		self._auth.prepare_auth_step(step, params, self.global_vars)

		if step['type'] == 'redirect':
			uri = self.config.make_uri(step['uri'])
			step_params = {}

			if step.get('parameters'):
				uri = "{}?{}".format(uri, urllib.urlencode(step['parameters']))

			return {'redirect': uri, 'step_id': step_id}
		elif step['type'] == 'endpoint':
			endpoint_name = step['endpoint']
			output = self.go(endpoint_name)

			# merge output of steps
			return_params = params.copy()
			return_params.update(output)
			return {'params': return_params, 'step_id': step_id}
		else:
			raise Exception('invalid step type')

	def go(self, endpoint_name, endpoint_vars = {}, local_vars = {}):
		if isinstance(local_vars, dict):
			self.local_vars = local_vars

		# must set endpoint name before checking for bypass_prerequisites
		self.config.custom_endpoint_name = endpoint_name
		self.config.set_actual_endpoint_name()
		self.config.apply_custom_endpoint_params()

		if not Utilities.dict_lookup(self.config.settings, 'endpoints', self.config.custom_endpoint_name, 'bypass_prerequisites'):
			self._process_prerequisites()

		# must set endpoint name after processing prerequisites to setup requested endpoint
		self.config.custom_endpoint_name = endpoint_name
		self.config.set_actual_endpoint_name()		
		self.config.apply_custom_endpoint_params()

		if self.config.actual_endpoint_name not in self.config.settings['endpoints']:
			raise Exception('specified endpoint does not exist in config: {}'.format(self.config['actual_endpoint_name']))

		if isinstance(endpoint_vars, dict):
			self.endpoint_vars = endpoint_vars
		else:
			self.endpoint_vars = {}

		array_set = endpoint_vars.get('array_set')

		if array_set:
			self.config.apply_endpoint_array_set_vars(array_set)

		self.config.apply_endpoint_vars(endpoint_vars)
		self.config.set_method()
		self._auth.setup_oauth_header(self.global_vars)

		self._time_limit = self.local_vars.get('time_limit') or self.config.get_custom_endpoint_setting('time_limit')
		output = self.request.get_response(self._time_limit)
		output_config = self.config.get_endpoint_setting('output')

		# filter output
		if output_config and 'filter' in output_config and Utilities.is_structure(output):
			unfiltered_output = list(output)
			output = []

			if not Utilities.is_structure(output_config['filter']):
				raise Exception('onfig endpoint output filter must be a structure')
				
			for filter in output_config['filter']:
				match_found = False

				if 'search_key' not in filter or 'search_value' not in filter:
					raise Exception('search_key and search_value are required for output filtering')
					
				for item in unfiltered_output:
					item_value = item.get(filter['search_key'])

					if item_value == None:
						continue

					if item_value == filter['search_value']:
						match_found = True

						if filter['return_key']:
							return item.get(filter['return_key'])

						output.append(item)

				if filter.get('return_type'):
					if filter['return_type'] == 'boolean':
						return match_found
					elif filter['return_type'] == '!boolean':
						return not match_found

		return output

	def _process_prerequisites(self):
		if Utilities.dict_lookup(self.config.settings,'endpoint_prerequisites'):
			if not isinstance(self.config.settings['endpoint_prerequisites'], list):
				raise Exception('endpoint_prerequisites must be an array')

			for prerequisite in self.config.settings['endpoint_prerequisites']:
				if not prerequisite.get('repeat') and self._prerequisites_complete:
					continue

				if prerequisite.get('protocol'):
					if prerequisite['protocol'] == 'cookie':
						cookie_file = "{}/sdkless_{}_cookie".format(tempfile.gettempdir(), self.api_name)

						if self.local_vars.get('cookie_id'):
							cookie_file = "{}_{}".format(cookie_file, self.local_vars['cookie_id'])
						
						self.config.settings['common_endpoint_settings']['all']['request_options']['COOKIEFILE'] = cookie_file
						self.config.settings['common_endpoint_settings']['all']['request_options']['COOKIEJAR'] = cookie_file

				if prerequisite.get('endpoint'):
					if not self.config.settings['endpoints'].get(prerequisite['endpoint']):
						raise Exception('specified prerequisite endpoint does not exist in config')

					self.config.custom_endpoint_name = prerequisite['endpoint']
					self.config.set_actual_endpoint_name()
					self.config.apply_custom_endpoint_params()

					response = self.request.get_response(self._time_limit)

					if response and prerequisite.get('merge_maps'):
						for response_key, merge_key in prerequisite['merge_maps'].items():
							if response.get(response_key):
								self.global_vars['merge'][merge_key] = response[response_key]

						self.config.apply_global_vars(self.global_vars)

			self.prerequisites_complete = True
