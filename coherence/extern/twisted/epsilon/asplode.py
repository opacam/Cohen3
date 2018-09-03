
import sys, os
from datetime import date

def status(x):
    sys.stderr.write(x+'\n')
    sys.stderr.flush()

def splode(linerator, proj, capproj):
    current = None
    for line in linerator:
        line = line.replace('_project_', proj)
        line = line.replace('_Project_', capproj)
        line = line.replace('_date_', str(date.today()))
        ls = line.split("###file:")
        if len(ls) > 1:
            fname = ls[1].strip()
            if current is not None:
                current.close()
            try:
                os.makedirs(os.path.dirname(fname))
            except:
                pass
            current = open(fname, 'wb')
            status('Created: ' + fname)
        else:
            current.write(line)
    current.close()

def main(argv):
    splode(sys.stdin.readlines(), 'zoop', 'Zoop')

if __name__ == '__main__':
    main(sys.argv)
