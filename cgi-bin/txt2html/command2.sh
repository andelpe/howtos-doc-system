#!/bin/bash 

BASEDIR=/var/www/cgi-bin/howtos/txt2html/

fname="$1"


rst2html -t --stylesheet ${BASEDIR}/mystyle2.css,${BASEDIR}/pygment.css \
   $fname | sed -e 's#class="upperalpha simple"#type="A"#' \
                -e 's#class="loweralpha simple"#type="a"#'


