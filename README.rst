*******
SamStat
*******

SamStat is a custom toolkit used in a bioinformatics pipeline.


The `qstat` script preforms the following operations on QNAMES from a SAM file:

1. Number of lines per QNAME
2. Number of unquie RNAMEs per QNAME
3. Range of RNAMEs per QNAME
4. Link attribute type of sequences using a corresponding GFF3 file from the same dataset

The `truedir` deduces the true direction of each sequence per-RNAME for every QNAME in a SAM file using a GFF3 file

Install:
--------

**requires python3**

::

  git clone https://github.com/willpatterson/SamStat.git
  cd SamStat
  python setup.py install

Usage:
------

::

  samstat <SAM_filepath> <GFF3_filepath> <Out_filepath>
  samstat --help 
  samstat -h
