#!/bin/bash 

BASEDIR=/var/www/cgi-bin/howtos/txt2html/

fname="$1"


out=$(rst2html -t --stylesheet ${BASEDIR}/mystyle2.css,${BASEDIR}/pygment.css \
   $fname 2> /tmp/rst2html.error | sed -e 's#class="upperalpha simple"#type="A"#' \
                                       -e 's#class="loweralpha simple"#type="a"#') 

if [ -s /tmp/rst2html.error ]; then 
  cat /tmp/rst2html.error
  exit 5
else
  echo "$out"
  exit 0
fi  

