#!/usr/bin/env python

import sys

from setuptools import setup, find_packages

if not sys.version_info[0] == 3:
    print('only python3 supported!')
    sys.exit(1)

setup(
    name='memeSHARK',
    version='2.0.1',
    author='Steffen Herbold',
    author_email='herbold@cs.uni-goettingen.de',
    description='Condense code entities to remove duplicates',
    install_requires=['mongoengine', 'pymongo', 'pycoshark>=1.0.21', 'networkx>=2.0', 'dictdiffer'],
    url='https://github.com/smartshark/memeSHARK',
    download_url='https://github.com/smartshark/memeSHARK/zipball/master',
    packages=find_packages(),
    test_suite='tests',
    zip_safe=False,
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache2.0 License",
        "Operating System :: POSIX :: Linux",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
