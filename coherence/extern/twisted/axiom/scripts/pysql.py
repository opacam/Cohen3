import sys
import traceback
from pprint import pprint

from coherence.extern.twisted.axiom._pysqlite2 import Connection

con = Connection.fromDatabaseName(sys.argv[1])
cur = con.cursor()

while True:
    try:
        cur.execute(input("SQL> "))
        results = list(cur)
        if results:
            pprint(results)
    except Exception as e:
        traceback.print_exc()
