import json
import copy
#
from utilities import Utilities
# require_once 'Exception.php'

class Configuration(object):
	def __init__(self, merge_open, merge_close):
		self.json = None
		self.json_custom = None
		self.settings = None
		self.settings_custom = None
		self.method = None
		self.custom_endpoint_name = None
		self.actual_endpoint_name = None

		self._merge_open = merge_open
		self._merge_close = merge_close

	def setup(self):
		try:
			settings = json.loads(self.json)
		except:
			raise Exception('invalid JSON in config file')

		self.settings = settings

		# custom config is optional
		if not self.json_custom:
			return

		try:
			settings = json.loads(self.json_custom)
		except:
			raise Exception('invalid JSON in custom config file')

		self.settings_custom = settings

	def set_actual_endpoint_name(self):
		# if passed endpoint_name is mapped in custom config, set to maps_to name 
		maps_to = Utilities.dict_lookup(self.settings_custom, 'endpoints', self.custom_endpoint_name, 'maps_to')

		if maps_to:
			self.actual_endpoint_name = maps_to
		else:
			self.actual_endpoint_name = self.custom_endpoint_name

	def set_method(self):
		method = Utilities.dict_lookup(self.settings, 'endpoints', self.actual_endpoint_name, 'method')

		if method:
			self.method = method
			return method

		method = Utilities.dict_lookup(self.settings, 'common_endpoint_settings', 'all', 'method')

		if method:
			self.method = method
			return method

		self.method = 'get'
		return method

	# populate settings with values from settings_custom
	def apply_custom_global_vars(self):
		global_merge = Utilities.dict_lookup(self.settings_custom, 'global', 'merge')

		if global_merge:
			settings = json.dumps(self.settings)

			for key, value in global_merge.items():
				merge_key = "{}{}{}".format(self._merge_open, key, self._merge_close)
				settings = settings.replace(merge_key, value)

			try:
				settings = json.loads(settings)
			except:
				raise Exception('invalid JSON caused by custom config global merge')

			self.settings = settings

		global_set = Utilities.dict_lookup(self.settings_custom, 'global', 'set')

		if global_set:
			for key, value in global_set.items():
				self.settings[key] = value

	def apply_custom_endpoint_params(self):
		custom_endpoint = Utilities.dict_lookup(self.settings_custom, 'endpoints', self.custom_endpoint_name)
		if custom_endpoint:
			if custom_endpoint.get('parameters'):
				Utilities.dict_nested_add(self.settings, {}, 'endpoints', self.actual_endpoint_name, 'parameters')

				for key, value in custom_endpoint['parameters'].items():
					self.settings['endpoints'][self.actual_endpoint_name]['parameters'][key] = value

			if custom_endpoint.get('output'):
				Utilities.dict_nested_add(self.settings, {}, 'endpoints', self.actual_endpoint_name, 'output')

				for key, value in custom_endpoint['output'].items():
					self.settings['endpoints'][self.actual_endpoint_name]['output'][key] = value

			if custom_endpoint.get('limit') is not None:
				Utilities.dict_nested_add(self.settings, custom_endpoint['limit'], 'endpoints', self.actual_endpoint_name, 'limit')

			if custom_endpoint.get('paging') is not None:
				Utilities.dict_nested_add(self.settings, custom_endpoint['paging'], 'endpoints', self.actual_endpoint_name, 'paging')

	# overwrite config_json w/ values from global_vars merge and set
	def apply_global_vars(self, global_vars):
		if global_vars.get('merge'):
			settings = json.dumps(self.settings)

			for key, value in global_vars['merge'].items():
				if key == 'OAUTH-HEADER-PARAMS':
					value = Utilities.add_slashes(value)
				
				settings = settings.replace("{}{}{}".format(self._merge_open, key, self._merge_close), value)

			try:
				settings = json.loads(settings)
			except:
				raise Exception('invalid JSON caused by global merge vars')

			self.settings = settings

		if global_vars.get('set'):
			self._apply_global_set_vars(global_vars['set'])

	def set_endpoint_setting(self, keys, value):
		new_keys = ['endpoints', self.actual_endpoint_name] + keys
		Utilities.dict_nested_update(self.settings, value, *new_keys)

	# populate settings with values from endpoint_vars['array_set'] (passed to SDKless::go)
	# recursive
	def apply_endpoint_array_set_vars(self, array_set):
		# create static method variables
		if not hasattr(Configuration.apply_endpoint_array_set_vars.__func__, 'new_endpoint_setting'):
			Configuration.apply_endpoint_array_set_vars.__func__.new_endpoint_setting = []

		if not hasattr(Configuration.apply_endpoint_array_set_vars.__func__, 'endpoint_setting_keys'):
			Configuration.apply_endpoint_array_set_vars.__func__.endpoint_setting_keys = []

		array_set_templates = Utilities.dict_lookup(self.settings_custom, 'endpoints', self.custom_endpoint_name, 'array_set_templates')

		if not array_set_templates:
			return

		for key, value in array_set.items():
			new_key = self._map_endpoint_parameter(self.custom_endpoint_name, key)
			Configuration.apply_endpoint_array_set_vars.__func__.endpoint_setting_keys.append(new_key)

			# when list is found, generate required format from template and populate
			# list must contain dict children
			if isinstance(value, list):
				template = array_set_templates.get(new_key)

				if not template:
					raise Exception("array_set_templates key {} does not exist in custom config".format(new_key))

				if not isinstance(template, str) and not isinstance(template, unicode) and not isinstance(template, dict):
					raise Exception('array_set template must be a string or a dict')

				for entry in value:
					if not isinstance(entry, dict):
						raise Exception('array_set must contain dictionaries to apply to template')

					if isinstance(template, str) or isinstance(template, unicode):
						new_template = entry.get(template)

						if new_template is None:
							raise Exception('array_set template key not found in array set')
					else:
						new_template = copy.deepcopy(template)

						for entry_key, entry_value in entry.items():
							self._update_template_value(new_template, entry_key, entry_value)

					Configuration.apply_endpoint_array_set_vars.__func__.new_endpoint_setting.append(new_template)

				self.set_endpoint_setting(Configuration.apply_endpoint_array_set_vars.endpoint_setting_keys, Configuration.apply_endpoint_array_set_vars.new_endpoint_setting)
				Configuration.apply_endpoint_array_set_vars.__func__.endpoint_setting_keys = []
				Configuration.apply_endpoint_array_set_vars.__func__.new_endpoint_setting = []
			elif isinstance(value, dict):
				self.apply_endpoint_array_set_vars(value)
			else:
				raise Exception('array set must contain dict and/or list')

	# populate settings with values from endpoint_vars (passed to SDKless::go), both merge and set
	def apply_endpoint_vars(self, endpoint_vars):
		if endpoint_vars.get('set'):
			self._apply_endpoint_parameter_maps(endpoint_vars['set'])
			self._apply_endpoint_set(endpoint_vars['set'])

		if endpoint_vars.get('merge'):
			settings = json.dumps(self.settings)

			for key, value in endpoint_vars['merge'].items():
				key = self._map_endpoint_parameter(self.custom_endpoint_name, key)
				settings = settings.replace("{}{}{}".format(self._merge_open, key, self._merge_close), value)

			try:
				settings = json.loads(settings)
			except:
				raise Exception('invalid JSON caused by endpoint merge vars')

			self.settings = settings

	def is_merged(self, value):
		if not isinstance(value, str) and not isinstance(value, unicode):
			return True

		if self._merge_open in value and self._merge_close in value:
			return False

		return True

	def make_uri(self, uri):
		base_uri = self.settings['base_uri']

		if not uri:
			uri = base_uri
			return uri

		# if uri is not full, concatenate with base uri
		if ('http://' not in uri.lower()) and ('https://' not in uri.lower()):
			uri = base_uri + uri

		return uri

	def get_custom_endpoint_setting(self, setting):
		return self._get_setting(self.settings_custom, self.custom_endpoint_name, setting)

	def get_endpoint_setting(self, setting):
		return self._get_setting(self.settings, self.actual_endpoint_name, setting)

	# only suporting one redirect step?
	def get_authentication_redirect_step_id(self):
		for i in range(len(self.settings['authentication']['steps'])):
			step = self.settings['authentication']['steps'][i]

			if step['type'] == 'redirect':
				return i

		return None

	def _get_setting(self, settings, endpoint_name, setting):
		# endpoint setting can be in endpoint, common_endpoint_settings[self.method], or common_endpoint_settings['all'] (in order of precedence)
		# check in order of precedence and immediately return if non-object
		# if have object(s), merge them in reverse order since the latter ones overwrite
		results = []
		setting_value = Utilities.dict_lookup(settings, 'endpoints', endpoint_name, setting)

		if setting_value is not None:
			if isinstance(setting_value, dict):
				results.append(setting_value)
			else:
				return setting_value

		setting_value = Utilities.dict_lookup(settings, 'common_endpoint_settings', self.method, setting)

		if setting_value is not None:
			if isinstance(setting_value, dict):
				results.append(setting_value)
			else:
				return setting_value

		setting_value = Utilities.dict_lookup(settings, 'common_endpoint_settings', 'all', setting)

		if setting_value is not None:
			if isinstance(setting_value, dict):
				results.append(setting_value)
			else:
				return setting_value

		if not results:
			return None

		ret = {}
		results.reverse()

		for s in results:
			for key, value in s.items():
				ret[key] = value

		self._clean_endpoint_setting(ret)

		return ret

	# recursive
	def _apply_global_set_vars(self, set_vars, keys=None):
		# keys is modified in this fuction, and will maintain it's values in subsequent calls; so we must reset it here if it is not passed
		if not keys:
			keys = []

		for key, value in set_vars.items():
			key = self._map_global_parameter(key)

			if isinstance(value, dict):
				keys.append(key)
				self._apply_global_set_vars(value, keys)
			else:
				destination = self.settings
				self.set_setting(destination, keys + [key], value)

	# get actual endpoint parameter name from custom one; from endpoint if exists, global if not
	def _map_endpoint_parameter(self, endpoint, param):
		endpoint_param = Utilities.dict_lookup(self.settings_custom, 'endpoints', endpoint, 'parameter_maps', param)

		if endpoint_param:
			return endpoint_param

		global_param = self._map_global_parameter(param)

		if global_param:
			return global_param

		return param

	def _map_global_parameter(self, param):
		param = Utilities.dict_lookup(self.settings_custom, 'global', 'parameter_maps', param)
		return param

	# find key in the template and replace the template value with the incoming value
	# recursive
	def _update_template_value(self, template, key, value):
		if not isinstance(template, dict):
			raise Exception('template must be a dict')

		for template_key, template_value in template.items():
			if isinstance(template_value, dict):
				self._update_template_value(template_value, key, value)
			else:
				if template_value == key:
					template[template_key] = value

	# update incoming keys to mapped keys
	# recursive
	def _apply_endpoint_parameter_maps(self, dic):
		count = len(dic)
		counter = 0

		if not isinstance(dic, dict):
			raise Exception('apply_endpoint_parameter_maps requires a structure')

		for key, value in dic.items():
			# changing array mid-loop can cause endless loop????
			if counter == count:
				break

			if isinstance(key, str):
				del dic[key]
				key = self._map_endpoint_parameter(self.custom_endpoint_name, key)
				dic[key] = value

			if isinstance(dic[key], dict):
				self._apply_endpoint_parameter_maps(dic[key])

			counter += 1

	# recursive
	def _apply_endpoint_set(self, set_values, keys=None):
		# keys is modified in this fuction, and will maintain it's values in subsequent calls; so we must reset it here if it is not passed
		if not keys:
			keys = []

		for key, value in set_values.items():
			if isinstance(value, dict):
				keys.append(key)
				self._apply_endpoint_set(value, keys)
			else:
				self.set_endpoint_setting(keys + [key], value)

	# recursive
	def _clean_endpoint_setting(self, setting):
		setting = copy.deepcopy(setting)

		if not isinstance(setting, dict):
			return

		for key, value in setting.items():
			if isinstance(value, dict):
				self._clean_endpoint_setting(value)
			else:
				do_unset = False

				if value is None:
					do_unset = True

				# skip params containing unmerged vars allows for optional params
				if not self.is_merged(value):
					do_unset = True

				if do_unset:
					del setting[key]
