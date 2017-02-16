import json
import urllib
import copy
import requests as requests_lib
from requests import Request as RequestsRequest, Session
from urlparse import parse_qs
#
from utilities import Utilities
from output import Output

class Request(object):

	def __init__(self, config):
		self.responses = {}
		self.last_status_code = None
		self._config = config
		self._output = Output()
		self._time_limit = None

	def get_response(self, time_limit):
		self.responses = {}
		self.last_status_code = None
		self._config.set_method()
		output = None
		total_count = 0
		paging_counter = None

		if not time_limit:
			time_limit = None

		# loop for paging
		while True:
			response = self._get(time_limit)

			if not response:
				break

			# populate_ret = self._output.populate(self._config, response, output)
			response_count, output = self._output.populate(self._config, response, output)
			# response_count = populate_ret['response_count']
			# output = populate_ret['output']

			if response_count == 0:
				break

			total_count += response_count
			limit = self._config.get_endpoint_setting('limit')

			# if total count >= limit, truncate/break
			if limit and (total_count >= limit):
				if isinstance(output, list):
					output = output[:limit]

				break

			# if paging, setup next page param
			paging = self._config.get_endpoint_setting('paging')

			if not paging or not paging['parameters']:
				break

			paging_type = paging.get('type', 'page_number')
			endpoint_params = self._config.get_endpoint_setting('parameters')
			page_size_param = paging['parameters']['page_size'].get('name', 'page_size') if 'page_size' in paging['parameters'] else 'page_size'
			page_size = endpoint_params.get(page_size_param) if endpoint_params else None
			paging_base = paging['parameters'][paging_type].get('base', 1) if paging_type in paging['parameters'] else 1

			# paging parameters can go in the payload data or query string
			paging_parameter_location = paging.get('parameter_location', 'data')

			if paging_type == 'page_number':
				try:
					paging_counter_param = Utilities.dict_lookup(paging, 'parameters', 'page_number', 'name')
				except:
					raise Exception('paging paging_type name required')

				if paging_counter == None:
					paging_counter = paging_base

				paging_counter += 1

				keys = ['parameters', paging_counter_param]
				self._config.set_endpoint_setting(keys, paging_counter)

				# response count is less than page size; break
				if page_size and (response_count < page_size):
					break
			elif paging_type == 'record_offset':
				try:
					paging_counter_param = Utilities.dict_lookup(paging, 'parameters', 'record_offset', 'name')
				except:
					raise Exception('paging paging_type name required')

				if paging_counter == None:
					paging_counter = paging_base

				if not page_size:
					raise Exception('endpoint page size parameter required for offset paging')

				paging_counter += page_size
				keys = ['parameters', paging_counter_param]

				self._config.set_endpoint_setting(keys, paging_counter)

				# response count is less than page size break
				if not page_size and (response_count < page_size):
					break
			elif paging_type == 'cursor':
				if not Utilities.dict_lookup(paging['parameters'], paging_type, 'location') or not isinstance(paging['parameters'][paging_type]['location'], list):
					raise Exception('paging paging_type location array required')

				data = copy.deepcopy(response)

				# drill down to new cursor uri
				for location_key in paging['parameters'][paging_type]['location']:
					data = data.get(location_key)
				
				if not data:
					break

				self._config.set_endpoint_setting(['uri'], data)

		return output

	def _get(self, time_limit):
		self._set_uri()
		headers = self._get_request_headers()
		data = self._get_request_data()
		auth_user = self._get_request_user()
		response = self._go(auth_user, headers, data, time_limit)
		output_format = self._config.get_endpoint_setting('output_format')

		if not self.responses.get(self._config.custom_endpoint_name):
			self.responses[self._config.custom_endpoint_name] = []

		if output_format == 'json':
			output = self._json_decode(response)
		elif output_format == 'json_text_lines':
			output = self._json_text_lines_decode(response.text)
		elif output_format == 'query_string':
			output = parse_qs(response.text)
		else:
			output = response.text

		self.responses[self._config.custom_endpoint_name].append(output)
		self._http_code_check(self.last_status_code)

		return output

	def _set_uri(self):
		uri = self._config.make_uri(self._config.get_endpoint_setting('uri'))
		uri_parts = uri.split('?')
		uri = uri_parts[0]
		params = self._config.get_endpoint_setting('parameters')

		# only add query string if it doesn't already exist
		# this is so that cursor paging can set a new uri w/ query string w/o having unwanted original endpoint params added
		if len(uri_parts) > 1:
			uri = '?'.join(uri_parts)
		else:
			if params and (self._config.method == 'get'):
				params = urllib.urlencode(params)
				uri = "{}?{}".format(uri, params)

		self.uri = uri
		return uri

	# returns request object
	def _go(self, auth_user, headers, data, time_limit):
		# print('*** uri')
		# print(self.uri)
		# print('*** method')
		# print(self._config.method)
		# print('*** headers variable')
		# print(headers)
		# print('*** data')
		# print(data)
		# print('*** time_limit')
		# print(time_limit)
		# print('*** auth_user')
		# print(auth_user)

		# print(self._config.get_endpoint_setting('request_options'))

		if self._config.method == 'post':
			response = requests_lib.post(self.uri, data=data, headers=headers, timeout=time_limit, auth=auth_user)
		elif self._config.method == 'put':
			response = requests_lib.put(self.uri, data=data, headers=headers, timeout=time_limit, auth=auth_user)
		elif self._config.method == 'delete':
			response = requests_lib.delete(self.uri, data=data, headers=headers, timeout=time_limit, auth=auth_user)
		else: # get
			# requests seems to automatically set some headers (Content-Length) that some API's don't like (Twitter needs Content-Length to be blank or omitted for GETs)
			# we deal with this by setting these headers in the the config file (see Twitter Content-Length set to 0) and then overwriting prepped headers
			s = Session()
			req = RequestsRequest('GET', self.uri, data=data, headers=headers, auth=auth_user)
			prepped = req.prepare()

			for key, value in headers.items():
				prepped.headers[key] = headers[key]

			response = s.send(prepped, timeout=time_limit)

		self.last_status_code = response.status_code

		# print('*** headers')
		# print(response.request.headers)
		# print('*** status_code')
		# print(response.status_code)
		# print('*** response text')
		# print(response.text)
		# print('*** response headers')
		# print(response.headers)

		return response

	def _get_request_headers(self):
		request_options = self._config.get_endpoint_setting('request_options')
		return request_options.get('headers') if request_options else None

	def _get_request_data(self):
		input_format = self._config.get_endpoint_setting('input_format')
		params = self._config.get_endpoint_setting('parameters')

		if input_format == 'json':
			params = json.dumps(params)
		elif input_format == 'query_string':
			params = urllib.urlencode(params)

		return params

	def _get_request_user(self):
		request_options = self._config.get_endpoint_setting('request_options')

		if request_options.get('user'):
			if not isinstance(request_options.get('user'), list) or (len(request_options.get('user')) < 2):
				raise Exception('request user must be a list containing name and api key')

			return (request_options.get('user')[0], request_options.get('user')[1])

		return None

	# check if returned code warrants an exception
	# supports any length code
	def _http_code_check(self, code):
		http_code_check = self._config.get_endpoint_setting('http_code_check')

		# if returned code doesn't start with the ok code
		if http_code_check and not str(code).startswith(str(http_code_check)):
			raise Exception('failed http code check')

	def _json_decode(self, response):
		try:
			output = response.json()
		except:
			self.responses[self._config.custom_endpoint_name].append(response.text)
			raise Exception('API returned invalid JSON')

		self._error_check(output)

		return output

	def _error_check(self, output):
		output_config = self._config.get_endpoint_setting('output')

		if not output_config:
			return

		error_location = Utilities.dict_lookup(output_config, 'error', 'location')

		if not error_location:
			return

		if not isinstance(error_location, list):
			self.responses[self._config.custom_endpoint_name].append(output)
			raise Exception('config error location must be an array')

		# drill down to desired data
		for location_key in error_location:
			output = output.get(location_key)

			if not output:
				break

		if output:
			self.responses[self._config.custom_endpoint_name].append(output)
			raise Exception("API returned error: {}".format(output))

	def _json_text_lines_decode(self, response):
		lines = response.strip().splitlines()
		headers = json.loads(lines.pop(0))
		output = []

		for line in lines:
			try:
				line = json.loads(line);
			except:
				raise Exception('API returned invalid JSON')

			contact = {}
			
			for index in range(len(line)):
				contact[headers[index]] = line[index]

			output.append(contact)

		return output
