#!/bin/bash 

BASEDIR=/var/www/cgi-bin/howtos/txt2html/

fname="$1"
page="$2"


html1="<center> \n <a href=\"/cgi-bin/howtos/howtos.py\">Back Home</a>  \&nbsp;\&nbsp;\&nbsp;\&nbsp;\&nbsp; \n  <a href=\"/cgi-bin/howtos/howtos.py?page=${page}\&action=edit\">Edit</a> \n</center>\n"

rst2html -t --stylesheet ${BASEDIR}/mystyle.css,${BASEDIR}/pygment.css \
   $fname | sed "/^<h1 class=\"title/s#^#$html1#"   
