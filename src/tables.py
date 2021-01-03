from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


class TokenTable(Base):
    __tablename__ = "tokens"

    token = Column(String, primary_key=True)
    description = Column(String)
    granted_tables = Column(postgresql.ARRAY(postgresql.TEXT, dimensions=1))


class BasesTable(Base):
    __tablename__ = "bases"

    type = Column(String)
    description = Column(String)
    name = Column(String, primary_key=True)
    ip = Column(String)
    port = Column(String)
    username = Column(String)
    password = Column(String)


class TablesInfoTable(Base):
    __tablename__ = "tables_info"

    table_name = Column(String)
    folder_name = Column(String)
    database_name = Column(String, ForeignKey("bases.name"), primary_key=True)
    local_name = Column(String)
    columns = Column(postgresql.JSON)