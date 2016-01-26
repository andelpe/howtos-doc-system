#!/usr/bin/env python 

import warnings
warnings.simplefilter('ignore', DeprecationWarning)


####   IMPORTS   ####
import sys, os, time
import json
import pickle
from optparse import OptionParser
import pymongo as m
from mongoIface import *


####   MAIN   ####
def main():
    """
     Performes the main task of the script (invoked directly).
     For information on its functionality, please call the help function.
    """
    
    # Options
    helpstr = """%prog [options] <howtos-dir>

Parses all howto files and generates a list of names with basic keywords (one per word in
the title (considering '-' as separator).
"""

    # Create parser with general help information
    parser = OptionParser(usage=helpstr, version="%prog-2.0")

    # Option verbose ('store_true' option type)
    helpstr = "Be verbose (show additional information)"
    parser.add_option("-v", "--verbose", dest="verb", help=helpstr, action="store_true")

    # Option usage 
    helpstr = "Show usage information"
    def myusage(option, opt, value, parser): 
        print parser.get_usage().split('\n')[0]
        sys.exit(0)
    parser.add_option("-u", "--usage", help=helpstr, action="callback",  
                      callback=myusage)
    def usage():
        print parser.get_usage().split('\n')[0]

    # Do parse options
    (opts, args) = parser.parse_args()

    # Shortcut for verbose
    verb = opts.verb
    
    # Args           
    if len(args)<1:
       err("Not enough input arguments!")
       usage()
       return 2
    dir = args[0]

    #### REAL MAIN ####

    # Get pointer to the data collection
    hList = getCollPointer()
        
    # Perform the parsing of the howto files
    parseDir(dir, hList, verb=verb)

    return True



###    SCRIPT    ####
if __name__=="__main__":
    sys.exit(main())
