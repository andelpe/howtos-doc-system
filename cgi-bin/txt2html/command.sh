#!/bin/bash 

BASEDIR=/var/www/cgi-bin/howtos/txt2html/

fname="$1"
page="$2"

filedate=`date -u '+%Y-%m-%d %H:%M UTC' -r $fname`

html1="<center>"
html1="$html1 \n <a href=\"/cgi-bin/howtos/howtos.py\">Back Home</a>  \&nbsp;\&nbsp;\&nbsp;\&nbsp;\&nbsp;"
html1="$html1 \n <a href=\"/cgi-bin/howtos/howtos.py?page=${page}\&format=txt\">txt</a> \&nbsp;\&nbsp;\&nbsp;"
html1="$html1 \n <a href=\"/cgi-bin/howtos/howtos.py?page=${page}\&format=twiki\">twiki</a> \&nbsp;\&nbsp;\&nbsp;\&nbsp;"
html1="$html1 \n <a href=\"/cgi-bin/howtos/howtos.py?page=${page}\&format=pdf\">pdf</a> \&nbsp;\&nbsp;\&nbsp;\&nbsp; \&nbsp;\&nbsp;\&nbsp;"
html1="$html1 \n <a href=\"/cgi-bin/howtos/howtos.py?page=${page}\&action=edit\"><font color=\"red\">Edit</font></a>"
html1="$html1 \n</center>\n"

rst2html -t --stylesheet ${BASEDIR}/mystyle.css,${BASEDIR}/pygment.css \
   $fname | sed -e "/^<h1 class=\"title/s#^#$html1#" \
                -e "s#Generated.*#Last update: \&nbsp;\&nbsp; $filedate. <br/>\n&#" \
                -e 's#class="upperalpha simple"#type="A"#' \
                -e 's#class="loweralpha simple"#type="a"#'


