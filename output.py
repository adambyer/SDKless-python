import copy
#
from utilities import Utilities

class Output(object):

	 # output starts as None
	 # if no output_config/output_format or output_format is not 'iterable'
	 # - if paging
	 # -- if response is array: output will be array merge of output and response
	 # -- otherwise (dict, scalar): output will be array of response items
	 # - if no paging
	 # -- output will be response
	def populate(self, config, response, output):
		self._config = config
		response_count = 0
		output_config = config.get_endpoint_setting('output')
		paging = config.get_endpoint_setting('paging')
		ret = {}

		if output == None:
			output = []

		if not output_config:
			if paging:
				if isinstance(response, list):
					return len(response), output + response
				else:
					output.append(response)
					return 1, output
			else:
				return 1, response

		data = self._get_data(response)

		if not data:
			return 0, output

		output_format = Utilities.dict_lookup(output_config, 'data', 'format')

		if output_format == 'iterable': # like an array of contact records
			if not Utilities.is_structure(data):
				raise Exception('output config specifies structure data format but response is not a structure');

			# put in specified output format, if applicable
			if Utilities.dict_lookup(output_config, 'data', 'items', 'locations'):
				if isinstance(data, dict):
					for data_key, data_value in data.items():
						key_filter = Utilities.dict_lookup(output_config, 'data', 'key_filter')

						if key_filter:
							if (key_filter == 'numeric') and not isinstance(data_key, int):
								continue
						
						# if output_config.data.items is specified, we are expecting the data structure to contain child structures
						if not Utilities.is_structure(data_value):
							raise Exception('output config specifies data items but response children are not structures')

						output_item = self._get_item(data_value);
						output.append(output_item)
						response_count += 1
				elif isinstance(data, list):
					for data_value in data:
						# if output_config.data.items is specified, we are expecting the data structure to contain child structures
						if not Utilities.is_structure(data_value):
							raise Exception('output config specifies data items but response children are not structures')

						output_item = self._get_item(data_value);
						output.append(output_item)
						response_count += 1
			else:
				output = output + data
				response_count = len(data)
		else: # non-iterable (like scalar value or single contact record)
			if isinstance(data, dict) and Utilities.dict_lookup(output_config, 'data', 'items', 'locations'):
				return_output = self._get_item(data)
			else:
				return_output = data # leave data as is

			if paging:
				output.append(return_output)
			else:
				output = return_output

			response_count = 1

		return response_count, output

	def _get_data(self, data):
		output_config = self._config.get_endpoint_setting('output')
		location = Utilities.dict_lookup(output_config, 'data', 'location')

		if not location:
			return data
		
		if not isinstance(location, list):
			raise Exception('endpoint output location must be a list')
		
		# drill down to desired data
		for location_key in location:
			data = data.get(location_key)

			if data == None:
				raise Exception("specified key not found in response: {}".format(location_key))

		return data

	def _get_item(self, data):
		output_config = self._config.get_endpoint_setting('output')
		output_item = {}

		for location_key, location in output_config['data']['items']['locations'].items():
			if isinstance(location, list):
				# location is an array like: ["email_addresses", 0, "email_address"],
				data_copy = copy.deepcopy(data)

				for location_item in location:
					if isinstance(location, dict):
						# if location item is a dict, this indicates a search; data must also be a dict
						output_item = self._set_item_by_search(data_copy, location_item, location_key, output_item);
					else:
						data_copy = data_copy.get(location_item)

						if data_copy == None:
							raise Exception('specified key not found in response: $location_item')

						output_item[location_key] = data_copy
			else:
				if location in data:
					output_item[location_key] = data[location]
				else:
					output_item[location_key] = None

		return output_item

	def _set_item_by_search(self, data, location_item, location_key, output_item):
		if not isinstance(data, dict):
			raise Exception('output data item must be a structure when config location item is a structure')
		
		if (not location_item.get('search_key')) or ('search_value' not in location_item) or ('return_key' not in location_item):
			raise Exception('search_key, search_value, and return_key are required when location item is a structure')

		search_key = location_item.search_key
		return_key = location_item.return_key

		for child_item in data:
			# if location item is a structure, data must be a structure
			if not isinstance(child_item, dict):
				raise Exception("output data item must be a dict when config location item is a dict")

			if (search_key in child_item) and (child_item['search_key'] == location_item['search_value']):
				output_item[location_key] = child_item[return_key]

		return output_item
