import uuid
import urllib
import hashlib
import collections
import hmac
import copy
import time
from random import random
#
from utilities import Utilities

class Authentication(object):

	def __init__(self, config):
		self._config = config

	#  add incoming params to outgoing parameters of current step
	#  parameter_maps (key/value) maps incoming keys (key) from previous step to required keys (value) for current step
	#  - if incoming key exists in parameter_maps of current step, use the associated value as the parameter key for current step
	def prepare_auth_step(self, step, incoming_params, global_vars):
		if incoming_params:
			if step['type'] == 'endpoint':
				if not Utilities.dict_lookup(self._config.settings, 'endpoints', step['endpoint']):
					return

				# merge incoming params with global_vars and re-setup config
				if Utilities.dict_lookup(self._config.settings, 'endpoints', step['endpoint'], 'merge_maps'):
					for incoming_key, merge_key in self._config.settings['endpoints'][step['endpoint']]['merge_maps'].items():
						if incoming_params.get(incoming_key):
							global_vars['merge'][merge_key] = incoming_params[incoming_key]

					self._config.apply_global_vars(global_vars)

				param_location = self._config.settings['endpoints'][step['endpoint']]
			else:
				param_location = step

			if param_location.get('parameter_maps'):
				for key, value in incoming_params.items():
					param_key = key;

					if param_location['parameter_maps'].get(key):
						param_key = param_location['parameter_maps'][key]
					
					if not param_location.get('parameters'):
						param_location['parameters'] = {}

					# if params are specified in config, only set those
					if param_location['parameters'].get(param_key):
						param_location['parameters'][param_key] = value
			else:
				# if parameters is a dict, merge in the incoming values; otherwise set parameters to None for next step
				if param_location.get('parameters') and isinstance(param_location.get('parameters'), dict):
					# if params are specified in config, only set those
					for key, value in param_location['parameters'].items():
						if incoming_params.get(key):
							param_location['parameters'][key] = incoming_params[key]
				else:
					param_location['parameters'] = None

	#  this happens last, before calling the API
	#  oauth_nonce, oauth_timestamp, and oauth_signature will be set here if not already set by global vars, endpoint vars, or custom config
	def setup_oauth_header(self, global_vars):
		self._config.set_method()
		request_params = self._config.get_endpoint_setting('parameters')
		include_oauth_header = self._config.get_endpoint_setting('include_oauth_header')

		if not include_oauth_header:
			return

		if not Utilities.dict_lookup(self._config.settings, 'authentication', 'oauth_header_parameters'):
			return

		oauth_nonce = hashlib.sha1(str(random())).hexdigest()
		oauth_timestamp = str(int(time.time()))
		oauth_params = self._get_oauth_params(oauth_nonce, oauth_timestamp)
		oauth_signature = self._get_oauth_signature(oauth_params, request_params)
		oauth_header_dict = {}

		for key, value in oauth_params.items():
			value = urllib.quote(value, safe='')
			oauth_header_dict[key] = '{}="{}"'.format(key, value)

		oauth_header_dict['oauth_signature'] = 'oauth_signature="{}"'.format(urllib.quote(oauth_signature, safe=''))
		oauth_header_ordered = [t[1] for t in sorted(oauth_header_dict.items())]
		global_vars['merge']['OAUTH-HEADER-PARAMS'] = ', '.join(oauth_header_ordered)

		self._config.apply_global_vars(global_vars);

	def _get_oauth_params(self, oauth_nonce, oauth_timestamp):
		oauth_header_parameters = self._config.settings['authentication']['oauth_header_parameters']
		params = {}

		for key, value in oauth_header_parameters.items():
			if key in ('oauth_consumer_secret', 'oauth_token_secret', 'oauth_signature'):
				value = None
			elif key == 'oauth_callback':
				if self._config.actual_endpoint_name != 'request_token':
					value = None
			elif key == 'oauth_nonce':
				value = oauth_nonce
			elif key == 'oauth_timestamp':
				value = oauth_timestamp

			if not value:
				continue

			if not self._config.is_merged(value):
				continue

			params[key] = value

		sorted_params = collections.OrderedDict(sorted(params.items()))
		return sorted_params

	# collect applicable oauth parameters from config:authentication:oauth_header_parameters and endpoint parameters
	# sort and encode with signing key
	def _get_oauth_signature(self, oauth_params, request_params):
		oauth_header_parameters = self._config.settings['authentication']['oauth_header_parameters']

		if not request_params:
			request_params = {}

		signature_params = copy.deepcopy(oauth_params)
		signature_params.update(request_params) 
		signature_pairs = []
		signature_params = collections.OrderedDict(sorted(signature_params.items()))

		for key, value in signature_params.items():
			if not value:
				continue

			value = urllib.quote(value, safe='')
			signature_pairs.append("{}={}".format(key, value))

		uri = self._config.make_uri(self._config.get_endpoint_setting('uri'))
		parameter_string = '&'.join(signature_pairs)
		signature_base_string = '&'.join([self._config.method.upper(), urllib.quote(uri, safe=''), urllib.quote('&'.join(signature_pairs))])
		signing_key = ''

		if oauth_header_parameters.get('oauth_consumer_secret') and self._config.is_merged(oauth_header_parameters['oauth_consumer_secret']):
			signing_key = urllib.quote(oauth_header_parameters['oauth_consumer_secret'], safe='') + '&'

		if oauth_header_parameters.get('oauth_token_secret') and self._config.is_merged(oauth_header_parameters['oauth_token_secret']):
			signing_key += urllib.quote(oauth_header_parameters['oauth_token_secret'], safe='')

		hashed = hmac.new(str(signing_key), str(signature_base_string), hashlib.sha1)
		oauth_signature = hashed.digest().encode('base64').rstrip('\n')
		
		# print("*** SDKless:Authentication::_get_oauth_signature:signature_params:")
		# print(signature_params)
		# print("*** SDKless:Authentication::_get_oauth_signature:signature_pairs:")
		# print(signature_pairs)
		# print("*** SDKless:Authentication::_get_oauth_signature:parameter_string:" + parameter_string)
		# print("*** SDKless:Authentication::_get_oauth_signature:signature_base_string:" + signature_base_string)
		# print("*** SDKless:Authentication::_get_oauth_signature:signing_key:" + signing_key)
		# print("*** SDKless:Authentication::_get_oauth_signature:oauth_signature:" + oauth_signature)

		return oauth_signature
