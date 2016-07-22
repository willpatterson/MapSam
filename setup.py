from setuptools import setup, find_packages
from setuptools.command.install import install

setup(name="SamLink",
      version="0.0.0",
      description="Pulls relivent data from .sam files and maps sam sequences onto a .gff file",
      license="MIT",
      author="William Patterson, Amie Romney",
      packages=find_packages(),
      install_requires=["BioPython", 'pysam'])

