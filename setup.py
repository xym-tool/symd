import os
from setuptools import setup

def read(fname):
	return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(name = 'symd',
      version='0.1',
      description='A tool to extract and display YANG module dependencies from IETF RFCs and Drafts',
      long_description=read('README.md'),
      packages = ['symd'],
      scripts = ['bin/symd'],
      author = 'Jan Medved',
      author_email = 'jmedved@cisco.com',
      license = 'New-style BSD',
      install_requires = ['networkx>=1.10', 'numpy>=1.10.1', 'matplotlib>=1.5.0'],
      include_package_data = True,
      keywords = ['yang', 'dependencies'],
      classifiers = []
)
