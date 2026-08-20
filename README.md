# CHD Converter for batches
This is a tool to simplify the task of converting files intended for some retro activities in linux distributions

there are a couple of parts to this program:

section 1: 
  CHD Batch converter
    This is the main tool, it does conversion from iso into chd, and can do a set list of files in sub session, 
    in an orderly manner to avoid crashing your systems. still caution is recommended as it will crash your system if not enough ram is provided, 
    as well as it will put your CPU to the limit at least as far as the test system 
    
    # PROPER COOLING is highly recomended
      
      This program does its work in 3 phases: 
          Phase 1: selection of files
          
          Phase 2: conversion of files
          
          Phase 3: verification of files, this will tell if any process was done incorrectly and how much space was trimmed out by converting into CHD

section 2: ape to flac pre-processor
    This tool will aid you convert *.ape into flac files to make the chd conversion easier

section 3: CHD Extractor
    This section is meant to aid with extraction only of certain types of files out of compressed directories

## NOTES:
as of V1.0.1 install.sh is broken

## RECOMENDED SPECS
- 16GB RAm
- Ryzen 5 3600 or similar 6 core procesor
- SATA SSD 
