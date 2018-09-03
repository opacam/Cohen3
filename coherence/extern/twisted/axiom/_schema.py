
# DELETE_OBJECT = 'DELETE FROM axiom_objects WHERE oid = ?'
CREATE_OBJECT = 'INSERT INTO *DATABASE*.axiom_objects (type_id) VALUES (?)'
CREATE_TYPE = 'INSERT INTO *DATABASE*.axiom_types (typename, module, version) VALUES (?, ?, ?)'


BASE_SCHEMA = ["""
CREATE TABLE *DATABASE*.axiom_objects (
    type_id INTEGER NOT NULL
        CONSTRAINT fk_type_id REFERENCES axiom_types(oid)
)
""",

"""
CREATE INDEX *DATABASE*.axiom_objects_type_idx
    ON axiom_objects(type_id);
""",

"""
CREATE TABLE *DATABASE*.axiom_types (
    typename VARCHAR,
    module VARCHAR,
    version INTEGER
)
""",

"""
CREATE TABLE *DATABASE*.axiom_attributes (
    type_id INTEGER,
    row_offset INTEGER,
    indexed BOOLEAN,
    sqltype VARCHAR,
    allow_none BOOLEAN,
    pythontype VARCHAR,
    attribute VARCHAR,
    docstring TEXT
)
"""]

TYPEOF_QUERY = """
SELECT *DATABASE*.axiom_types.typename, *DATABASE*.axiom_types.module, *DATABASE*.axiom_types.version
    FROM *DATABASE*.axiom_types, *DATABASE*.axiom_objects
    WHERE *DATABASE*.axiom_objects.oid = ?
        AND *DATABASE*.axiom_types.oid = *DATABASE*.axiom_objects.type_id
"""

HAS_SCHEMA_FEATURE = ("SELECT COUNT(oid) FROM *DATABASE*.sqlite_master "
                      "WHERE type = ? AND name = ?")

IDENTIFYING_SCHEMA = ('SELECT indexed, sqltype, allow_none, attribute '
                      'FROM *DATABASE*.axiom_attributes WHERE type_id = ? '
                      'ORDER BY row_offset')

ADD_SCHEMA_ATTRIBUTE = (
    'INSERT INTO *DATABASE*.axiom_attributes '
    '(type_id, row_offset, indexed, sqltype, allow_none, attribute, docstring, pythontype) '
    'VALUES (?, ?, ?, ?, ?, ?, ?, ?)')

ALL_TYPES = 'SELECT oid, module, typename, version FROM *DATABASE*.axiom_types'

GET_GREATER_VERSIONS_OF_TYPE = ('SELECT version FROM *DATABASE*.axiom_types '
                                'WHERE typename = ? AND version > ?')

SCHEMA_FOR_TYPE = ('SELECT indexed, pythontype, attribute, docstring '
                   'FROM *DATABASE*.axiom_attributes '
                   'WHERE type_id = ?')

CHANGE_TYPE = 'UPDATE *DATABASE*.axiom_objects SET type_id = ? WHERE oid = ?'

APP_VACUUM = 'DELETE FROM *DATABASE*.axiom_objects WHERE (type_id == -1) AND (oid != (SELECT MAX(oid) from *DATABASE*.axiom_objects))'

