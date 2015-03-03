import subprocess as sub
import sys, os, signal
import re
from math import log
import threading

class SimpleConfigParser:
  def __init__(self):
      self.vars = {}

  def read(self, filename):

      f = open(filename)
      try:
          # May raise IOError
          lines = f.readlines()
      finally:
          f.close()
          
      for line in lines:
          line = line.strip()
          if (not line) or (line.startswith('#')):
              continue
          tokens = line.split("=")
          key = tokens[0].strip()
          key = key.strip("\"")
          value = tokens[1].strip()
          value = value.strip("\"")
      
          self.vars[key] = value

  def get(self, keyname):
      try:
         return self.vars[keyname]
      except KeyError:
         return None

  def list(self):
      return self.vars.keys()

  def dump(self):
      return self.vars


class ArrayParser:
  def __init__(self):
      self.vectors = []

  def read(self, filename):

      # May raise IOError
      fp = open(filename)
         
      while(True):
        line = fp.readline()
        if not line:
            break
        if line.strip() == '' or line[0] in '#':
            continue
        tokens = line.split()
        self.vectors.append(tokens)

      fp.close()
        
  def get(self, keyname):
      result = []
      for v in self.vectors:
         if v[0] == keyname: result.append(v)
      return result

  def list(self):
      return self.vectors


def countLines(filename):
      # May raise IOError
      fp = open(filename)
         
      nlines = 0
      while(True):
        line = fp.readline()
        if not line:
            break
        if line.strip() == '' or line[0] in '#':
            continue
        
        nlines = nlines + 1
        
      fp.close()

      return nlines



def isNumber(x):
  """
   Returns true if the argument is a number object or a string
   convertible to number.
  """
  try:
    float(x)
    return True
  except:
    return False


def parseLine(s, skipComments = False):
    """
    Splits passed string s using blank as separator, but joining
    together those tokens enclosed within double commas (""). 
    The double commas themselves are eliminated.

    If skipComments is set to True, for strings starting with '#', 
    returns an empty list.
    """
    if not s: 
        return []
    if skipComments:
        s = s.strip()
        if not s:
           return []
        if s[0] == '#':
            return []
    tokens = s.split()
    to_del = []
    vals = range(len(tokens))
    for i in vals:
#        print tokens[i]
        if tokens[i][0] == '"':
             for j in vals[i+1:]:
#                 print " ",tokens[j]
                 if tokens[j][-1] == '"':
                     tokens[i] = tokens[i][1:]
                     for k in vals[i+1:j]:
#                     print "   ",tokens[k]
                         tokens[i] += " "+tokens[k]
                         to_del.insert(0, k)
                     tokens[i] += " "+tokens[j][:-1]
                     to_del.insert(0, j)
                     vals = range(len(tokens))
                     break
#            print tokens

    for item in to_del:
       tokens.pop(item)

    return tokens

def err(msg=''):
    """
    Prints the specified string msg to standard error (with an added trailing newline)
    """
    sys.stderr.write(msg+'\n')


## TODO: This does not work because of locals not going into the function
##       But it is a good idea!
#def show(*exprs):
#    """
#    Prints the specified expressions literally together with their evaluation
#    """
#    for expr in exprs:
#        print "%s: %s" % (expr, eval(expr))


class commandError(Exception):
    """
    Exception class to be thrown when there are problems running an
    external program with the 'shell', 'cmd', 'shellerr' functions.
    """
    # We add nothing to our base class
    pass


def shellerr(command, bg = False):
    """
    Runs the specified command (string) in a shell and returns the output 
    of the command (stdout and stderr) in a list like:
       [stdout, stderr]
       
    If the command exits with non-zero status, a commandError exception is
    raised, containing exit code, stdout and stderr.

    If 'bg' is set to True, then it does not wait for process completion just 
    launches it and returns None.
    """
    res = None
    fnull = open(os.devnull, 'w')
    if bg:  f = fnull
    else:   f = sub.PIPE

    p = sub.Popen(command, shell = True, stdout=f, stderr=f, stdin=fnull)

    if not bg:
        res = p.communicate()
        p.wait()

        # If error, raise exception
        if p.returncode:
            raise commandError(p.returncode, res[0], res[1])
      
    # Else, return output
    return res


#def shell(command):
#    """
#    Runs the specified command (string) in a shell and returns the output 
#    of the command (stdout and stderr together with 2>&1) and its exit code
#    in a list like:
#       [output, exitcode]
#    """
#    res = shellerr(command + ' 2>&1')
#    return [res[0], res[2]]


def shell(command, input=None, ignoreError=False, bg=False, tout=None):
    """
    Runs the specified command (string) in a shell and returns the output 
    of the command (stdout and stderr together with 2>&1).
    
    If 'input' is specified and different from None, it is passed to the stdin
    of the command.

    If the command exits with non-zero status, a commandError exception is
    raised (including a message with the output).    

    If 'bg' is set to True, then it does not wait for process completion just 
    launches it and returns None. Ignored if 'input' is set.
    """

    def target(vars, command, input, ignoreError, bg):

        if input == None: 
            fin = open(os.devnull, 'w')
            if bg:  fout = fin
            else:   fout = sub.PIPE
        else:
            fin = sub.PIPE
            fout = sub.PIPE

        vars[1] = sub.Popen(command+' 2>&1', shell=True, stdout=fout, stdin=fin,
                            preexec_fn=os.setsid)

        if input:     vars[0] = vars[1].communicate(input=input)
        elif not bg:  vars[0] = vars[1].communicate()

        if input or (not bg):
            vars[1].wait()
            if vars[0]:  vars[0] = vars[0][0]
            
            # If error, return an exception
            if vars[1].returncode and (not ignoreError):
                msg = 'Error in "%s". Exit code: %s. Output: %s'
                msg = msg % (command, vars[1].returncode, vars[0])
                vars[0] = commandError(msg)


    # Thread
    vars = [None, None]
    thargs = [vars, command, input, ignoreError, bg]
    thread = threading.Thread(target=target, args=thargs)
    thread.start()
    thread.join(tout)
    if not sys.version.startswith('2.4'):
        if thread.is_alive():  
#            vars[1].terminate()
            os.killpg(vars[1].pid, signal.SIGTERM)
            msg = "Command timed out"
            raise commandError(msg)

    # Return result (or raise exception)
    if type(vars[0]) == commandError:  raise vars[0]
    return vars[0]


def cmd(command):
    """
    Runs the specified command (string or list) without a shell and returns the 
    output of the command (stdout and stderr) in a list like:
       [stdout, stderr]

    If the command exits with non-zero status, a commandError exception is
    raised, containing exit code, stdout and stderr.
    """
    try:
        args = command.split()
    except:
        args = command

    p = sub.Popen(args, shell = False, stdout=sub.PIPE, stderr=sub.PIPE)
    res = p.communicate()
    p.wait()

    # If error, raise exception
    if p.returncode:
        raise commandError(p.returncode, res[0], res[1])

    # Else, return output
    return res


def invFunc(n):
    """
    Returns a functions to invert binary numbers of 'n' bits.
    Example:
        inv = invFunc(4)
        inv(0b0100) 
          --> returns 0b1011
    """
    def inv(x):
        return ~x + 2**n
    return inv
inv = invFunc(8)


def padFunc(n):
    """
    Returns a functions to pad binary numbers to complete 'n' bits 
    (and remove leading '0b' prefix).
    Example:
        pad = padFunc(4)
        pad(0b10) 
          --> returns '0010'
    """
    def pad(x):
        s = bin(x).split('0b')[1]
        return '0'*(n-len(s)) + s
    return pad
pad = padFunc(8)


def flipFunc(n):
    """
    Returns a functions to flip binary numbers of 'n' bits 
    (and remove leading '0b' prefix).
    Example:
        flip = flipFunc(6)
        flip(0b10) 
          --> returns '010000'
    """
    def flip(x):
        res = ''
        for i in pad(x): res = i + res
        return res
    return flip
flip = flipFunc(8)


def maskToDec(mask):
    """
    Passes from x.x.x.x string or [x, x, x, x] (list of ints) mask to its decimal 
    integer (num bits) representation.
    """
    res = 0
    if type(mask) == str:
        mask = [int(x) for x in mask.split('.')]
    for dec in mask:
        val = eval('0b'+ flip(dec))
        res += log(val+1, 2)
    return int(res)


def DecToMask(mask):
    """
    Pass from decimal integer (num bits) mask to its [x, x, x, x] (list of ints) 
    representation.
    """
    res = []
    for i in range(int(mask / 8.0)):
       res.append(255)
    mod = int(mask % 8.0)
    if mod:
        res.append(eval('0b'+ flip(2**mod-1)))
#        res.append((2**mod-1) << (8-mod))
    for i in range(4 - len(res)):
        res.append(0)
    return res


def netmask(subnet, mask):
    """
    Parses specified subnet (as x.x.x.x string) and mask (as decimal integer
    (number of bits) or x.x.x.x string) and returns the range of IPs that this 
    subnet encompasses.
    """
    ini = [int(x) for x in subnet.split('.')]
    if type(mask) == int:  mask = DecToMask(mask)
    else:                  mask = [int(x) for x in mask.split('.')]
    end = []
    num = 0
    for i in range(4):
        end.append(ini[i] | inv(mask[i]))
    iniD = '.'.join([str(x) for x in ini])
    iniB = '.'.join([pad(x) for x in ini])
    endD = '.'.join([str(x) for x in end])
    endB = '.'.join([pad(x) for x in end])
#    print 'From %s to %s' % (iniD, endD)
    print '\n From %s   |    From  %s  to  %s' % (iniB, iniD, endD)
    decMask = maskToDec(mask)
    print '  to  %s   |    Mask: %s, /%s' % (endB, '.'.join([str(x) for x in mask]), decMask)
    print
    varbits = endB.count('1') - iniB.count('1')
    warn = ''
    if varbits != (32 - decMask):
        warn = '  NOT MATCHING GIVEN MASK (should be /%s)' % (32 - varbits)
    print ' ==> %s varying bits, %s different IPs %s' % (varbits, 2**varbits, warn)
    print



def unindent(lines, verb = False):
    """
    Unindents received text (by deleting leading blanks) so that there is at 
    least one line starting at first column (no blank offset). The other lines 
    are moved to the left the same number of spaces.

    Returns a list of lines of the same length of the input one.
    """
    pat = re.compile('[^ ]')

    # Let's get the spaces for each line (empty lines are not accounted for)
    offs = []
    for line in lines:
        m = pat.search(line.rstrip('\n'))
        if m:  offs.append(m.start())
        else:  offs.append(10000)
    if verb: print ' -- Offset list: %s' % offs

    # Calculate the minimum offset (skew)
    if not offs: return lines
    skew = min(offs)
    if verb: print ' -- Skew: %s' % skew

    # Unindent
    if skew:
        res = []
        for i, line in enumerate(lines):
            if line: res.append(line.replace(' ', '', skew))
            else:    res.append('')
    else:
        res = lines

    return res
     

def atoi(text):
    """
    Returns an integer version of the specified string if it is convertible,
    or the same string if not.
    """
    if text.isdigit(): return int(text)
    else:              return text


def ntokens(text):
    """
    Tokenizes the passed string and returns a list of these tokens after
    converting to int those that represent so.
    
    This function can be used as the 'key' parameter of the 'sort' function
    to correctly sort lists of elements with embedded numerical indices.
    See: http://nedbatchelder.com/blog/200712/human_sorting.html

    Example:
      l = ['gaeds001_1', 'gaeds001_10', 'gaeds001_2']
      l.sort(key=ntokens)
      print l
        ==> ['gaeds001_1', 'gaeds001_2', 'gaeds001_10']
    """
    return [ atoi(c) for c in re.split('(\d+)', text) ]


def human(val, bytes=False):
    """
    Returns a a human-readable string representing the passed number ('val'),
    by using K, M, G... prefixes (powers of 1000).

    If 'bytes' is set as True then powers of 1024 are used instead (i.e. 'K' means 'kibi'
    instead of 'kilo', 'M' means 'mebi' instead of 'mega', etc.

    Remember that you can also print in scientific notation just with sth like:
       print "%.2e" % val
    """
    factor = 1000.0
    extra = ''
    if bytes: 
        factor = 1024.0
        extra = 'i'

    for suff in ['','K','M','G','T','P','E']:
        if val < factor:
            return "%3.2f %s%s" % (val, suff, extra)
        val /= factor
