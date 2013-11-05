#!/bin/bash 

BASEDIR=/var/www/cgi-bin/howtos/txt2html/

rst2html -t --stylesheet ${BASEDIR}/mystyle.css,${BASEDIR}/pygment.css  $*
