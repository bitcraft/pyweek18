#!/usr/bin/env python
#encoding: utf-8

from setuptools import setup


setup(name="Bats and Castles",
      version='0.0.1',
      description='Simple Game - python3',
      author='bitcraft',
      packages=['castlebats'],
      install_requires=['pygame',
                        'pymunk',
                        'pymunktmx',
                        'pytmx',
                        'pyscroll'],
      license="LGPLv3",
      long_description='see https://github.com/bitcraft/castlebats',
      classifiers=[
          "Intended Audience :: Developers",
          "Development Status :: 4 - Beta",
          "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
          "Programming Language :: Python :: 3.3",
          "Topic :: Games/Entertainment",
      ],
)
