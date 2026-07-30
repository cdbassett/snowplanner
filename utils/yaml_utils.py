import yaml
import collections
import six

    # extra crap so unicode strings and order dicts look normal
def dict_representer(dumper, data):
#        return dumper.represent_dict(data.iteritems())
    return dumper.represent_dict((str(k), v) for k,v in six.iteritems(data))

def tuple_representer(dumper, data):
    return dumper.represent_list(data)
#        return repr(data)

class CleanDumper(yaml.dumper.Dumper):
   pass

CleanDumper.add_representer(str, yaml.representer.SafeRepresenter.represent_str)

if six.PY2:
    CleanDumper.add_representer(unicode, yaml.representer.SafeRepresenter.represent_unicode)

CleanDumper.add_representer(collections.OrderedDict, dict_representer)
CleanDumper.add_representer(tuple, tuple_representer)


def outputYAMLFile(filename, data, indent=4):
    with open(filename, 'wb') as outfile:
        yaml.dump(data, outfile, encoding='utf-8', allow_unicode=True, default_flow_style=False, Dumper=CleanDumper, width = 1024, indent=indent)

def outputYAMLtoOpenFile(outfile, data, indent=4):
    yaml.dump(data, outfile, encoding='utf-8', allow_unicode=True, default_flow_style=False, Dumper=CleanDumper, width = 1024, indent=indent)

def getYAMLString(data, indent=4):
    return yaml.dump(data, encoding='utf-8', allow_unicode=True, default_flow_style=False,Dumper=CleanDumper, width = 1024, indent=indent).decode("utf-8")

