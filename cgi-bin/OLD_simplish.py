#!/usr/bin/env python
# -*- coding: latin-1 -*-

####   IMPORTS   ####
import sys, re
from utils import err, shell, shellerr
from optparse import OptionParser
import tempfile


####   CONSTANTS   ####
psconf = """@page {
 margin-left: 2.5cm;
 margin-right: 2.5cm;
 margin-top: 0.8cm;
 margin-bottom: 1.6cm;
}
"""


####   CLASSES  ####
class text(object):
    """
    Class that encapsulates original TXT contents and produces HTML output.
    """

    # Class variables (constants)
    reT1 = re.compile('^\s*\*\*\** *$')
    reT2 = re.compile('^\s*===* *$')
    reT3 = re.compile('^\s*---* *$')
    reList = re.compile('^\s\s*-')
    reSpaces = re.compile('^\s\s*')
    reEmpty = re.compile('^\s*$')
    reLiter = re.compile('"(.*?)"')
    reBold = re.compile("\*(.*?)\*")
    reTitle = re.compile("\<h[1-9]\>")
    reImage = re.compile("^\s*\|IMAGE:(.*)\|(.*)\|$")
    patH = '%s <a name="%s">%s</a>'
    patH1 = '\n<br/><h1>'+patH+'</h1>'
    patH2 = '\n<br/><h2>'+patH+'</h2>'
    patH3 = '\n<br/><h3>'+patH+'</h3>'
    tab = '&emsp;'*2


    def __init__(self, lines, verb=False):
        """
        Constructor
        """
        self.lines = lines
        self.verb = verb

        self.titles = []
        self.pres = []
        self.inPre = False
        self.empty = []
        self.br = []
        self.literals = []
        self.bolds = []
        self.tcontents = {}
        self.tcontents[0] = "<br/><u><b>Table of contents</b></u><br/>"
        self.lists = []
        self.listWidth = 0
        self.images = []


    def toHtml(self):
        """
        Parses and processes input lines and produces output out of them.
        Creates the HTML and returns it as a string.

        Call it just once!
        """
        self._parse()
        self._processHtml()
        self._createHtml()
        return self.html


    def toPs(self, outf):
        """
        Generates PS output (it calls toHtml to convert from its result).

        Returns the name of a temporary file where the PS is stored.
        """
        # Generate HTML
        self.toHtml()

        # Prepare conf file
        tempconf = tempfile.mkstemp()[1]
        f = open(tempconf, 'w')
        f.write(psconf)
        f.close()

        # Prepare temporary HTML file
        temphtml = tempfile.mkstemp()[1]
        f = open(temphtml, 'w')
        f.write(self.html)
        f.close()

        # Convert from HTML to PS
        cmd = 'html2ps -d -f %s %s > %s' % (tempconf, temphtml, outf)
        if self.verb: print 'Running: %s' % cmd
        shellerr(cmd)


    def toPdf(self, outf):
        """
        Generates PDF output (it calls toHtml to convert from its result).
        
        Returns the name of a temporary file where the PDF is stored.
        """
        tempps   = tempfile.mkstemp()[1]
        self.toPs(tempps)
        cmd = 'ps2pdf -sPAPERSIZE=a4 %s %s' % (tempps, outf)
        if self.verb: print 'Running: %s' % cmd
        shell(cmd)


    def _addTitle(self, level, nline):
        """
        Helper function for titles found in the parsing of the text.
        """
        self.titles.append((level, nline))
        self.changes[0] = True
        self._mayClosePre(nline-1)
        self._mayCloseList(nline-1)
        noSpace = True


    def _mayClosePre(self, nline):
        """
        If we are in a preformatted block, set the end of it.
        """
        if self.inPre:
            self.pres.append(nline-1) 
            self.inPre = False
            self.changes[1] = True


    def _mayCloseList(self, nline):
        """
        If we are in a list, set the end of it.
        """
        if self.listWidth:
            self.lists[-1][-1].append(nline-1)
            self.listWidth = 0
            self.changes[2] = True


    def _checkInlines(self, line, nline):
        """
        Check if there are literals or bold patterns in the passed line.
        """

        # Literals
        if self.reLiter.search(line):  
            self.literals.append(nline)

        # Bolds
        if self.reBold.search(line):  
            self.bolds.append(nline)


    def _mayCloseSth(self, nline):
        """
        Checks if the line closes a list or a pre.
        """
        # End of list ?
        self._mayCloseList(nline)

        # End of preformatted ?
        self._mayClosePre(nline)


    def _showMainVars(self, onChange = None):
        """
        Print main vars result of the parsing. If onChange is not None, it should
        be a list of booleans, each one indicating if the corresponding main
        var should be printed or not.
        """
        if not onChange: flags = [True, True, True, True]
        else:            flags = onChange
        if flags[0]:  print '   self.titles--> %s' % self.titles
        if flags[1]:  print '   self.pres  --> %s' % self.pres
        if flags[2]:  print '   self.lists --> %s' % self.lists
        if flags[3]:  print '   self.images--> %s' % self.images


    def _parse(self):
        """
        Parse the text and take note of important constructs.
        """

        if self.verb: print 'Parsing file\n'
        self.changes = [False, False, False, False]

        for i, line in enumerate(self.lines[:]):

            s = line[0:-1]

            if self.verb: 
                print '%3d: %s' % (i, s)
                if self.changes != [False, False, False, False]:
                    print 
                    self._showMainVars(onChange=self.changes)
                    print 

            noSpace = False
            self.changes = [False, False, False, False]
            
            self.lines[i] = s

            # Titles
            if self.reT1.search(s):   
                self._addTitle(1, i)
            elif self.reT2.search(s): 
                self._addTitle(2, i)
            elif self.reT3.search(s): 
                self._addTitle(3, i)

            # Empty line --> add line break
            elif self.reEmpty.search(s): 
                if self.inPre: continue
                if self.listWidth: continue

                if (not i) or  noSpace:
                    self.br.append(i)
                else:
                    self.empty.append(i)
                    noSpace = True

            # Image
            elif self.reImage.search(s): 
                if self.inPre: continue
                self.images.append(i)
                self.changes[3] = True

            # List item
            elif self.reList.search(s): 

                # In any case, check the inline constructs
                self._checkInlines(s, i)

                # Take note of indentation width
                width = s.index('-')

                # If in list, check if we are at the same level we were
                if self.listWidth:
                    # If so, we are closing (and opening) a list item
                    if width == self.listWidth:  
                        self.lists[-1][-1].append(i)
                        self.lists[-1].append([i])
                        self.changes[2] = True
                        self._mayClosePre(i)
#                        continue
                    continue

                    # If in pre, ignore it will be considered regular pre text
                    # (we don't support lists within lists/pre),
                    if self.inPre: continue

#                    # Less deep: Close current list and new list item to outer list
#                    elif width < self.listWidth:
#                        self._mayCloseList(i)
#                        self.lists[-1].append([i])
#                        continue
#                    # Deeper list: Start new list (go on as if coming from normal text)

                # Coming from normal text (or increasing depth): start new list and list item
                self.lists.append([[i,]])
                self.listWidth = s.index('-')
                self.changes[2] = True

            # Indented --> preformatted or list continuation
            elif self.reSpaces.search(s): 

                if self.listWidth:
                    m = self.reSpaces.search(s)
                    # If continuation of a list, parse inline constructions
                    if m.end() == (self.listWidth + 2):
                        self._checkInlines(s, i)
                        continue
#                    # If finishing a list, close it
#                    else:
#                        self.lists[-1][-1].append(i)
#                        self.changes[2] = True

                # Start of preformatted
                if not self.inPre:
                    self.pres.append(i) 
                    self.inPre = True
                    self.changes[1] = True

            # Normal lines
            else:
                self._mayCloseSth(i)

                # Inline constructs
                self._checkInlines(s, i)

        # On end of text, perform the closing tests again
        self._mayCloseSth(i+1)


    def _processHtml(self):
        """
        Process the text to change it from TXT to HTML.
        """

        # If verb, show what we have
        if self.verb:
            print '\nProcessing HTML\n'
            self._showMainVars()

        # Before adding HTML tags, perform all coding replacements
        for i in range(len(self.lines)):
            self.lines[i] = self.lines[i].replace('&', '&amps;')
            self.lines[i] = self.lines[i].replace('<', '&lt;')
            self.lines[i] = self.lines[i].replace('>', '&gt;')
            self.lines[i] = self.lines[i].replace('á', '&aacute;')
            self.lines[i] = self.lines[i].replace('é', '&eacute;')
            self.lines[i] = self.lines[i].replace('í', '&iacute;')
            self.lines[i] = self.lines[i].replace('ó', '&oacute;')
            self.lines[i] = self.lines[i].replace('ú', '&uacute;')

        # Titles 
        headers = [self.patH1, self.patH2]
        spaces = ['', self.tab]
        tlevels = [x[0] for x in self.titles]
        tlines = [x[1] for x in self.titles]
        if 2 in tlevels:
            headers.append(self.patH3)
            spaces.append(2*self.tab)
        else:
            headers.append(self.patH2)
            spaces.append(self.tab)
        self._processTitlesHtml(self.titles, headers, spaces, tlevels)

        # Preformatted sections
        for i in range(0, len(self.pres), 2): 
            start = self.pres[i]
            if not self.reTitle.search(self.lines[start]):
                self.lines[start] = '<pre>' + self.lines[start]
                if len(self.pres) > i+1:
                    end = self.pres[i+1]
                    self.lines[end] =  self.lines[end] + '</pre>'

        # Images  -->  |IMAGE:/home/delgadop/fotos/IMG_7225.JPG|
        for i in self.images:
            m = self.reImage.search(self.lines[i])
            self.lines[i] = '<img src="%s" width="%s">' % (m.group(1), m.group(2))

        # Lists
        for list in self.lists:
            for elem in list:
                self.lines[elem[0]] = '<li>' + self.lines[elem[0]].replace('-', ' ', 1)
                self.lines[elem[1]-1] = self.lines[elem[1]-1] + '</li>'
            self.lines[list[0][0]]= '<ul>\n' + self.lines[list[0][0]]
            self.lines[list[-1][1]] = self.lines[list[-1][1]] + '\n</ul>'

        # Empty lines
        for i in self.empty:
            self.lines[i] += '<p/>'
        for i in self.br:
            self.lines[i] += '<br/>'

        # Literals
        for i in self.literals:
            self.lines[i] = self.reLiter.sub('<tt>\\1</tt>', self.lines[i])

        # Bolds
        for i in self.bolds:
            self.lines[i] = self.reBold.sub('<b>\\1</b>', self.lines[i])

        # Table of contents (already filled in the titles processing)
        # Insert it after the doc title (higher level if only one title)
        # or at the beginning of the document (if no single title at any level))
        if len(self.tcontents) > 2:
            self.tcontents[max(self.tcontents.keys())+1] = '<p/>'
            where = -1
            for level in 1, 2, 3:
                if tlevels.count(level) == 1:
                    where = self.titles[tlevels.index(level)][1]
                    break
                elif tlevels.count(level) > 1:
                    break

            cont = 0
            for i in sorted(self.tcontents.keys()):
                self.lines.insert(where+1+cont, self.tcontents[i])
                cont += 1

        # Now complete all lines with a line break
        for i in range(len(self.lines)):
            self.lines[i] += ' \n'



    def _processTitlesHtml(self, titles, headers, spaces, tlevels):
        """
        Loop on text and replace title text lines with <h%> constructions
        and delete title bar lines.
        """
        c1 = tlevels.count(1)
        c2 = tlevels.count(2)
        c3 = tlevels.count(3)
#        print 'c1,c2,c3:', c1,c2,c3
        x, y, z = 0, 0, 0
        extra = ''
        for level, nline in titles:

            if level == 1:
                extra = '<br/>'
                x += 1
                y = z = 0
                if c1 == 1: num = ''
                else:       num = '%s -' % x

            if level == 2:
                if 3 in tlevels:  extra = '<br/>'
                y += 1
                z = 0
                if (c1 == 0) and (c2 == 1): 
                    num = ''
                elif c1 in (0,1):
                    num = '%s -' % (y)
                else:
                    num = '%s.%s -' % (x, y)

            if level == 3:
                extra = ''
                z += 1
                if (c1 == 0) and (c2 == 0) and (c3 == 1): 
                    num = ''
                elif ((c1==0) and (c2 in (0,1))) or ((c1==1) and (c2==0)):
                    num = '%s -' % (z)
                elif (c1 in (0,1)) and (c2>0):
                    num = '%s.%s -' % (y, z)
                elif (c1>1) and (c2==0):
                    num = '%s.%s -' % (x, z)
                else:
                    num = '%s.%s.%s -' % (x, y, z)

            t = self.lines[nline-1].strip()
            if t:
                self.lines[nline-1] = headers[level-1] % (num, nline, self.lines[nline-1])
                self.lines[nline] = ''
                self.tcontents[nline] = '%s<br/>' % extra + spaces[level-1] + '<a href="#%s">%s %s</a>' % (nline, num, t)


    def _createHtml(self):
        """
        Produce HTML out of the transformed lines.
        """
        if self.verb:
            print '\nCreating HTML\n'
        self.html = '<html>\n<head></head>\n<body style="width:22cm">\n'
        for line in self.lines:
            self.html += line 
        self.html += '</body>\n</html>'


####   FUNCTIONS   ####


####   MAIN   ####
def main():
    """
     Performes the main task of the script (invoked directly).
     For information on its functionality, please call the help function.
    """
    
    # Options
    helpstr = """%prog [options] [<input-file>]

It parses specified input file (or standard input if none is given) and translates it
into HTML, which is shown in standard output, unless --html option is used (in which
case, output is stored in specified file). Options --ps or --pdf can be used to 
generate ps or pdf files instead of HTML.
"""

    # Create parser with general help information
    parser = OptionParser(usage=helpstr, version="%prog-2.0")

    helpstr = "Be verbose (show additional information)"
    parser.add_option("-v", "--verbose", dest="verb", help=helpstr, action="store_true")

    helpstr = "Produce ps output and store in file"
    parser.add_option("--ps", dest="fps", help=helpstr, action="store")

    helpstr = "Produce PDF output and store in file"
    parser.add_option("--pdf", dest="fpdf", help=helpstr, action="store")

    helpstr = "Store HTML output in file"
    parser.add_option("--html", dest="fhtml", help=helpstr, action="store")

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

    if ((opts.fps and (opts.fpdf or opts.fhtml)) or (opts.fpdf and (opts.fps or opts.fhtml))):
        err('Only one (or none) of --ps/--pdf/--html options can be specified')
        return 3

    # Shortcut for verbose
    verb = opts.verb
    
    #### REAL MAIN ####
    if args:
        f = open(args[0])
        lines = f.readlines()
        f.close()
    else:
        lines = sys.stdin.readlines()

    # Create text object
    t = text(lines, verb=verb)

    # PS
    if opts.fps:
        t.toPs(opts.fps)
    # PDF
    elif opts.fpdf:
        t.toPdf(opts.fpdf)
    # HTML
    else:
        out = t.toHtml()
        if opts.fhtml:
            f = open(opts.fhtml, 'w')
            f.write(out)
            f.close()
        else:
            print out
     
    # Exit successfully
    return 0


###    SCRIPT    ####
if __name__=="__main__":
    sys.exit(main())



