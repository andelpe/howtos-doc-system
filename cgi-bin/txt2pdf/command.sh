
# TODO: if we want to pass more options, etc, will need to properly parse command line...

in="$1"
out="$2"

tempdir=`mktemp -d`

BASEDIR="/var/www/cgi-bin/howtos/txt2pdf"
#cd $BASEDIR

rst2latex --stylesheet=${BASEDIR}/mystyle.sty --documentclass=report --use-docutils-toc "$1"  > ${tempdir}/myfile.tex

cd ${tempdir}
pdflatex  myfile.tex >/dev/null 2>&1

mv "${tempdir}/myfile.pdf"  "$2"

