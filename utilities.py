class Utilities(object):
	
	@staticmethod
	def is_structure(value):
		return (isinstance(value, list) or isinstance(value, dict))

	# drill down to, and return, value in nested dicts
	# usage example:
	## d = {'a':{'b':{'c':5}}}
	## lookup(d, 'a', 'b', 'c')
	@staticmethod
	def dict_lookup(dic, key, *keys):
		if keys:
			return Utilities.dict_lookup(dic.get(key, {}), *keys)

		return dic.get(key)

	# drill down to, and add, value in nested dicts, only if key doesn't exist
	# adding nested dicts as needed
	@staticmethod
	def dict_nested_add(dic, value, key, *keys):
		if keys:
			if not dic.get(key):
				dic[key] = {}

			Utilities.dict_nested_add(dic[key], value, *keys)
		elif not dic.get(key):
			dic[key] = value

	# drill down to, and add or update, value in nested dicts
	# adding nested dicts as needed
	@staticmethod
	def dict_nested_update(dic, value, key, *keys):
		if keys:
			if not dic.get(key):
				dic[key] = {}

			Utilities.dict_nested_update(dic[key], value, *keys)
		else:
			dic[key] = value

	@staticmethod
	def add_slashes(s):
		return s.replace("'", "\\'").replace('"', '\\"').replace("\\", "\\")
