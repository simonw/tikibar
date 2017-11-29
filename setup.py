#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

import tikibar

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

version = tikibar.__version__

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    os.system('python setup.py bdist_wheel upload')
    sys.exit()

if sys.argv[-1] == 'tag':
    print("Tagging the version on github:")
    os.system("git tag -a %s -m 'version %s'" % (version, version))
    os.system("git push --tags")
    sys.exit()

readme = open('README.rst').read()
# Replace the title underline '====' from the ReST of the changelog
# with simple underline '---'
history = open('CHANGELOG.txt').read().replace('=========', '---------')

setup(
    name='tikibar',
    version=version,
    description="""A debugging toolbar for Django""",
    long_description=readme + '\n\n' + history,
    author='Eventbrite, Inc.',
    author_email='opensource@eventbrite.com',
    url='https://github.com/eventbrite/tikibar',
    packages=[
        'tikibar',
    ],
    include_package_data=True,
    install_requires=[
    ],
    license="BSD",
    zip_safe=False,
    keywords='tikibar',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    ],
)
