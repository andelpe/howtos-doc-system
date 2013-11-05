#!/usr/bin/env python
# -*- coding: latin-1 -*-

####   IMPORTS   ####
import sys, re
from utils import err, shell, shellerr, unindent
from optparse import OptionParser
import tempfile


####   CONSTANTS   ####
BG_CODE = '<div class="preblock">'
BG_CODE_END = '</div>'

psconf = """@page {
 margin-left: 2.5cm;
 margin-right: 2.5cm;
 margin-top: 0.8cm;
 margin-bottom: 1.6cm;
}
"""

syntaxInfo = """
The input text file needs to follow some simple rules. Remember that the main goals of the 
syntax are that the text be easily understandable in its text format (and, of course, in the
resulting outputs) and that adjusting to the syntax adds no effort to the process of
writing (i.e.: it should be as simple as writing in free format).

  Normal text - Start the line in the leftmost column. Just that.

  Preformatted blocks of text (code) - Indent the text one space or more.
  Example:
    |This is normal text:
    |   And this is preformatted


  Titles - Underline the title with a single line of marks. The hierarchy of marks is the
  following:
    1st title: ************************
    2nd title: ========================
    3rd title: ------------------------
  Example: 
     |   This is a title
     |   ---------------
    

  Inline formatted text (literals) - Enclose the text between double commas: "text"
  Example:
    |Within normal text line, "this is a literal"


  Lists - Start the list element with one or more spaces, a dash, and a single space.
          Then, the text. If the next text line belongs to the same list element, it
          must start with spaces until the position where text started in the previous
          line. The next element of the list must start exactly as the first line
          of the previous element.
  Example:
    |   - This is a list element that spans
    |     two lines of text
    |         - This is a sublist elem
    |         - Second element in the sublist
    |   - This is a second element of the outer list


Elements that make sense only on the processed output formats (and not on the text
version of the document).

  Images -  |IMAGE|<img-file-path>|<width>|
  Links  -  |LINK|<url>|<link-text>|
  Autolinks  -  |<prot>://<url>|
"""


####   CLASSES  ####
class Lists(object):
    """
    Container for list elements or sublists. 
    """

    def __init__(self, ini, offset, parent = None):
        """
        Constructor.
        @ini: initial line of the List.
        @offset: offset of the List (for the '-' character)
        @parent: pointer to the List containing this one
        """
        self.ini = ini
        self.end = None
        self.offset = offset
        self.elems = []
        self.sublists = []
        self.pointer = self
        self.parent = parent
   

    def __str__(self):
        """
        Serialize object as a string.
        """
        # Ini
        result = '\n%s%s -: ' % (' '*self.offset, self.ini)

        # Elements
        if self.sublists and self.elems:
            result += '\n' + ' '*self.sublists[0].offset
        result += ', '.join(['(%s-%s)' % (x[0], x[1] if len(x)>1 else None) for x in self.elems])

        # Sublists
        for sublist in self.sublists:
            result += '%s' % sublist

        # End 
        if self.sublists: 
            result += '\n%s%s :-' % (' '*self.offset, self.end)
        else:
            result += ' :- %s' % (self.end)

        return result


    def newElem(self, ini):
        """
        Open a new list element specifying the initial line of that element.
        """
        self.elems.append([ini])


    def closeElem(self, end):
        """
        Close the last element of the list specifying the last line of that element.
        """
        if self.elems and (len(self.elems[-1])<2):
            self.elems[-1].append(end)


    def setPointer(self, obj):
        """
        Make the pointer of this List and of every parent point to the specified 'obj'.
        """
        self.pointer = obj
        if self.parent:
            self.parent.setPointer(obj)


    def newSublist(self, ini, offset):
        """
        Adds a new sublist specifying the initial line and offset for it. Make the 
        'currently used list' pointer point to the new sublist.
        """
        sublist = Lists(ini, offset, parent=self)
        self.sublists.append(sublist)
        self.setPointer(self.sublists[-1])


    def close(self, end):
        """
        Close current List; i.e.: set the 'end' element to specified line and set our
        parent's pointer to himself (rather than us).
        """
        self.end = end
        self.setPointer(self.parent)


    def isEmpty(self):
        """
        Returns True if this List is empty (i.e.: does not contains elements) and
        False otherwise.
        """
        if self.elems: return False
        return True


    def isLeaf(self):
        """
        Returns True if this List is leaf (i.e.: contains no sublists) and
        False otherwise.
        """
        if self.sublists: return False
        return True



class text(object):
    """
    Class that encapsulates original TXT contents and produces HTML output.
    """

    # Class variables (constants)
    reT1 = re.compile('^\s*\*\*\** *$')
    reT2 = re.compile('^\s*===* *$')
    reT3 = re.compile('^\s*---* *$')
    reList = re.compile('^\s\s*-\s')
    reSpaces = re.compile('^\s\s*')
    reEmpty = re.compile('^\s*$')
    reLiter = re.compile('"(.*?)"')
    reBold = re.compile("\*(.*?)\*")
    reLink = re.compile("\|LINK\|(.*)\|(.*)\|")
    reAutolink = re.compile("\|(.*://.*)\|")
    reTitle = re.compile("\<h[1-9]\>")
    reImage = re.compile("^\s*\|IMAGE\|(.*)\|(.*)\|$")
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
        self.lists = Lists(0, 0)
        self.images = []
        self.links = []


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
        self._mayCloseList(nline-1, 0)
        noSpace = True


    def _mayClosePre(self, nline):
        """
        If we are in a preformatted block, set the end of it.
        """
        if self.inPre:
            self.pres.append(nline-1) 
            self.inPre = False
            self.changes[1] = True


    def _mayCloseList(self, nline, offset):
        """
        If we are in a list, set the end of all the inner ones.
        """
        if self.lists.pointer.offset:
            self.lists.pointer.closeElem(nline-1)
            while offset < self.lists.pointer.offset:
                    self.lists.pointer.close(nline-1)
            self.changes[2] = True


    def _checkInlines(self, line, nline):
        """
        Check if there are literals, links or bold patterns in 
        the passed line.
        """

        # Literals
        if self.reLiter.search(line):  
            self.literals.append(nline)

        # Bolds
        if self.reBold.search(line):  
            self.bolds.append(nline)

        # Links
        if self.reLink.search(line): 
            self.links.append(nline)

        # Auto links
        if self.reAutolink.search(line): 
            self.links.append(nline)

    def _mayCloseSth(self, nline):
        """
        Checks if the line closes a list or a pre.
        """
        # End of list ?
        self._mayCloseList(nline, 0)

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
        if flags[3]:  print '   self.links--> %s' % self.links


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
                if self.lists.pointer.offset: continue

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
    
                # Take note of indentation offset
                offset = s.index('-')

                # If at the same offset level, we are closing (and opening) an item
                if offset == self.lists.pointer.offset:
                    self.lists.pointer.closeElem(i-1)
                    self.lists.pointer.newElem(i)
                    self.changes[2] = True
                    self._mayClosePre(i)
                    continue

                # If in pre, ignore it will be considered regular pre text
                # (we don't support lists within pre),
                if self.inPre: continue

                # Less deep: Close open list item and sublists and start new elem in outer list
                if offset < self.lists.pointer.offset:
                    self._mayCloseList(i, offset)
                    self.lists.pointer.newElem(i)
                    continue

                # Normal text or deeper list: close list elem (if any), start new list and list item
                self.lists.pointer.closeElem(i-1)
                self.lists.pointer.newSublist(i, offset)
                self.lists.pointer.newElem(i)
                self.changes[2] = True

            # Indented --> preformatted or list continuation
            elif self.reSpaces.search(s): 

                if self.lists.pointer.offset:
                    m = self.reSpaces.search(s)
                    # If continuation of a list, parse inline constructions
                    if m.end() == (self.lists.pointer.offset + 2):
                        self._checkInlines(s, i)
                        continue

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

        # Close external Lists list
        self.lists.close(i)


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
                # Unindent pre sections
                if len(self.pres) > i+1: end = self.pres[i+1]
                else:                    end = len(self.lines) - 2
                self.lines[start:end+1] = unindent(self.lines[start:end+1], self.verb)
                # Now add the <pre> tags
                self.lines[start] = BG_CODE + '<pre>' + self.lines[start]
                self.lines[end] =  self.lines[end] + '</pre>' + BG_CODE_END
#                if len(self.pres) > i+1:
#                    end = self.pres[i+1]
#                    self.lines[end] =  self.lines[end] + '</pre>'

        # Images  -->  |IMAGE|/home/delgadop/fotos/IMG_7225.JPG|<width>|
        for i in self.images:
            m = self.reImage.search(self.lines[i])
            self.lines[i] = '<img src="%s" width="%s">' % (m.group(1), m.group(2))

        # Lists
        self._processList(self.lists)

        # Empty lines
        for i in self.empty:
            self.lines[i] += '<p/>'
        for i in self.br:
            self.lines[i] += '<br/>'

        # Literals
        for i in self.literals:
            self.lines[i] = self.reLiter.sub('<span class="lit">\\1</span>', self.lines[i])

        # Links -->  |LINK|http://www.google.es|go to google|
        # Autolinks --> |http://www.google.es|
        for i in self.links:
            m = self.reLink.search(self.lines[i])
            if m:
                self.lines[i] = self.reLink.sub('<a href="%s">%s</a>' % (m.group(1), m.group(2)), self.lines[i])
            else:
                m = self.reAutolink.search(self.lines[i])
                self.lines[i] = self.reAutolink.sub('<a href="%s">%s</a>' % (m.group(1), m.group(1)), self.lines[i])

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


    def _processList(self, l):
        """
        Given the specified list 'l', recursively process the contained sublists,
        and for the list elements, add the appropriate HTML tags.
        """
        if self.verb: print 'In _processList: %s, %s' %(l.ini, l.isEmpty())
        if not l.isEmpty():
            for elem in l.elems:
                self.lines[elem[0]] = '<li>' + self.lines[elem[0]].replace('-', ' ', 1)
                self.lines[elem[1]] = self.lines[elem[1]] + '</li>'
            self.lines[l.ini]= '<ul>\n' + self.lines[l.ini]
            self.lines[l.end]= self.lines[l.end] + '\n</ul>'

        for sublist in l.sublists:
            self._processList(sublist)


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
        self.html = """<html>\n<head>
<link rel="stylesheet" type="text/css" href="/static/simplish.css">
</head>\n<body style="width:25cm">\n"""
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

For information on simplish syntax (how to format the text input file), please run 
'%prog --syntax'.
"""

    # Create parser with general help information
    parser = OptionParser(usage=helpstr, version="%prog-2.0")

    helpstr = "Show information on simplish syntax."
    parser.add_option("--syntax", dest="syntax", help=helpstr, action="store_true")

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

    if opts.syntax:
        print syntaxInfo
        return 0

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



