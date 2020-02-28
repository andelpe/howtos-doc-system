#!/bin/bash 

#BASEDIR=/var/www/cgi-bin/howtos/txt2html/
BASE=/howto/css

fname="$1"

# NOTE: instead of embedding, we link CSS styles, so that generated HTML is lighter,
#       and changes are applied without needing to run 'rst2html' again.
#       To share outside CIEMAT, we should use PDF (or, in the future, a public-IP server)

#out=$(rst2html -t --no-compact-lists --stylesheet ${BASEDIR}/mystyle2.css,${BASEDIR}/pygment.css \

out=$(rst2html -t --no-compact-lists --link-stylesheet \
      --stylesheet ${BASE}/howtostyle.css,${BASE}/pygment.css,${BASE}/html4css1.css \
      $fname 2> /tmp/rst2html.error | sed -e 's#class="upperalpha simple"#type="A"#' \
                                       -e 's#class="loweralpha simple"#type="a"#') 

if [ -s /tmp/rst2html.error ]; then 
  cat /tmp/rst2html.error
  exit 5
else
  echo "$out"
  exit 0
fi  

