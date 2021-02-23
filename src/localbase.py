import datetime
from typing import List

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from exceptions import AccessAlreadyGrantedError
from exceptions import DatabaseAlreadyExistsError
from exceptions import TableNotFoundError
from tables import BasesTable
from tables import TablesInfoTable
from tables import TokenTable
from utils import database_health_check
from utils import get_db_engine
from utils import get_existing_data


class LocalBaseWorker:
    def __init__(
        self,
        ip="localhost",
        user="postgres",
        password="password",
        database_name="postgres",
    ):
        self.db_session = self._get_connection(ip, user, password, database_name)

    @staticmethod
    def _get_connection(
        ip: str, user: str, password: str, database_name: str
    ) -> Session:
        return Session(
            bind=create_engine(f"postgresql://{user}:{password}@{ip}/{database_name}")
        )

    def add_database(
        self, base_type, description, local_name=None, **con_params
    ) -> str:
        if not database_health_check(get_db_engine(base_type, **con_params)):
            raise ConnectionError("Can't connect to database")
        if not local_name:
            local_name = "_".join(
                [
                    con_params["ip"],
                    con_params["port"],
                    con_params["database"],
                    con_params["user"],
                ]
            )
        if self._is_db_exists(local_name):
            raise DatabaseAlreadyExistsError(local_name)
        new_database = BasesTable(
            type=base_type, description=description, local_name=local_name, **con_params
        )

        self.db_session.add(new_database)
        self.db_session.commit()

        return local_name

    def get_database_and_connection(self, local_base_name: str):
        database_obj = (
            self.db_session.query(BasesTable)
            .filter_by(local_name=local_base_name)
            .first()
        )

        return database_obj, get_db_engine(
            database_obj.type,
            ip=database_obj.ip,
            port=database_obj.port,
            username=database_obj.username,
            database=database_obj.database,
            password=database_obj.password,
        )

    def write_table_params(
        self,
        table_name: str,
        folder_name: str,
        database_name: str,
        columns: dict,
        local_name: str = None,
    ) -> str:

        if not local_name:
            local_name = "_".join([database_name, folder_name, table_name])

        new_table = TablesInfoTable(
            table_name=table_name,
            folder_name=folder_name,
            local_name=local_name,
            database_name=database_name,
            columns=columns,
        )

        exist_obj = (
            self.db_session.query(TablesInfoTable)
            .filter_by(local_name=new_table.local_name)
            .first()
        )
        if not exist_obj:
            self.db_session.add(new_table)
        else:
            for attr in ["table_name", "folder_name", "database_name", "columns"]:
                setattr(exist_obj, attr, getattr(new_table, attr))
        self.db_session.commit()
        return local_name

    def get_table(
        self,
        database_name: str = None,
        folder_name: str = None,
        table_name: str = None,
        local_table_name: str = None,
    ) -> TablesInfoTable:
        return (
            self.db_session.query(TablesInfoTable)
            .filter_by(local_name=local_table_name)
            .first()
            if local_table_name
            else self.db_session.query(TablesInfoTable)
            .filter_by(
                database_name=database_name,
                folder_name=folder_name,
                table_name=table_name,
            )
            .first()
        )

    def get_table_params(self, local_table_name: str) -> dict:
        table_obj = self.get_table(local_table_name=local_table_name)
        return {
            "table_name": table_obj.table_name,
            "folder_name": table_obj.folder_name,
            "database_name": table_obj.database_name,
            "columns": table_obj.columns,
        }

    def get_database_object(self, local_database_name: str) -> BasesTable:
        return (
            self.db_session.query(BasesTable)
            .filter_by(local_name=local_database_name)
            .first()
        )

    def get_database_data(self, local_database_name: str):
        obj = self.get_database_object(local_database_name)
        return {
            "ip": obj.ip,
            "port": obj.port,
            "username": obj.username,
            "local_name": obj.local_name,
        }

    def get_db_name_list(self) -> list:
        return get_existing_data(self.db_session, BasesTable, "local_name")

    def get_local_name_list(self) -> list:
        return get_existing_data(self.db_session, TablesInfoTable, "local_name")

    def add_token(self, name: str, new_token: str, description: str, is_admin=False):
        new_token = TokenTable(
            name=name,
            token=new_token,
            description=description,
            granted_tables=[],
            admin_access=is_admin,
            create_date=datetime.datetime.now(),
        )

        self.db_session.add(new_token)
        self.db_session.commit()

    def get_user_tokens_objects_list(self) -> List[TokenTable]:
        # Returns only tokens without admin access
        return [
            i
            for i in get_existing_data(self.db_session, TokenTable)
            if not i.admin_access
        ]

    def get_admin_tokens_objects_list(self) -> List[TokenTable]:
        # Returns only tokens with access
        return [
            i for i in get_existing_data(self.db_session, TokenTable) if i.admin_access
        ]

    def get_tokens_list(self) -> List[str]:
        return [i.token for i in get_existing_data(self.db_session, TokenTable)]

    def get_tokens_names_list(self) -> List[str]:
        return [i.name for i in self.get_user_tokens_objects_list()]

    def add_table_for_token(
        self,
        token: str,
        database_name: str = None,
        folder_name: str = None,
        table_name: str = None,
        local_table_name: str = None,
    ):
        if not local_table_name:
            local_table_name = self.get_local_table_name(
                database_name=database_name,
                folder_name=folder_name,
                table_name=table_name,
            )
        row = self.db_session.query(TokenTable).filter_by(token=token).first()

        if not self.is_table_exists(local_table_name=local_table_name):
            raise TableNotFoundError(local_table_name)
        if local_table_name in self.get_token_tables(token):
            raise AccessAlreadyGrantedError(local_table_name)
        row.granted_tables = row.granted_tables + [local_table_name]

        self.db_session.commit()

    def get_local_table_name(
        self,
        database_name: str,
        folder_name: str,
        table_name: str,
    ):
        table_object = (
            self.db_session.query(TablesInfoTable)
            .filter_by(
                database_name=database_name,
                folder_name=folder_name,
                table_name=table_name,
            )
            .first()
        )
        return table_object.local_name if table_object else None

    def get_token_tables(self, token: str) -> list:
        return (
            self.db_session.query(TokenTable)
            .filter_by(token=token)
            .first()
            .granted_tables
        )

    def is_table_exists(
        self,
        database_name: str = None,
        folder_name: str = None,
        table_name: str = None,
        local_table_name: str = None,
    ):
        return (
            (
                self.db_session.query(TablesInfoTable)
                .filter_by(local_name=local_table_name)
                .first()
                is not None
            )
            if local_table_name
            else (
                self.db_session.query(TablesInfoTable)
                .filter_by(
                    database_name=database_name,
                    folder_name=folder_name,
                    table_name=table_name,
                )
                .first()
            )
            is not None
        )

    def get_base_of_table(
        self,
        database_name: str = None,
        folder_name: str = None,
        table_name: str = None,
        local_table_name: str = None,
    ):
        return (
            (
                self.db_session.query(TablesInfoTable)
                .filter_by(local_name=local_table_name)
                .first()
                .database_name
            )
            if local_table_name
            else (
                self.db_session.query(TablesInfoTable)
                .filter_by(
                    database_name=database_name,
                    folder_name=folder_name,
                    table_name=table_name,
                )
                .first()
                .database_name
            )
        )

    def get_db_type(
        self, local_table_name: str = None, local_db_name: str = None
    ) -> str:
        if local_table_name:
            local_db_name = (
                self.db_session.query(TablesInfoTable)
                .filter_by(local_name=local_table_name)
                .first()
                .database_name
            )
        return (
            self.db_session.query(BasesTable)
            .filter_by(local_name=local_db_name)
            .first()
            .type
        )

    @property
    def is_main_admin_token_exists(self) -> bool:
        return "main admin token" in get_existing_data(
            self.db_session, TokenTable, "description"
        )

    def _is_db_exists(self, local_database_name: str) -> bool:
        return local_database_name in get_existing_data(
            self.db_session, BasesTable, "local_name"
        )

    def get_local_database_name(self, ip: str, port: str, database: str) -> str:
        return (
            self.db_session.query(TablesInfoTable)
            .filter_by(
                ip=ip,
                port=port,
                database=database,
            )
            .first()
            .local_name
        )

    def get_database_tables(self, database_name: str):
        tables = get_existing_data(self.db_session, TablesInfoTable)

        return [i.local_name for i in tables if i.database_name == database_name]

    @staticmethod
    def add_test_token():
        """
        TEMP METHOD TO PREPARE DATABASE FOR TESTS
        """
        # Set admin token
        db_str = "postgresql://postgres:password@localhost/postgres"
        internal_db_engine = create_engine(db_str)
        import pandas as pd

        pd.DataFrame(
            [["admin-test-token", "main admin token", [], True]],
            columns=["token", "description", "granted_tables", "admin_access"],
        ).to_sql(
            "tokens",
            if_exists="append",
            index=False,
            con=internal_db_engine,
            schema="public",
        )

    def change_local_name(
        self, change_type: str, old_local_name: str, new_local_name: str
    ):
        """
        :param change_type: table or database (what change local name of)
        :param old_local_name: old table or db local name
        :param new_local_name: new table or db local name
        """
        if change_type == "database":
            db_obj = self.get_database_object(old_local_name)
            db_obj.local_name = new_local_name
        if change_type == "table":
            table_obj = self.get_table(local_table_name=old_local_name)

            # if just set new local name we get " duplicate key value violates unique constraint"
            # that's why we need to replace entire object
            new_table_obj = TablesInfoTable(
                local_name=new_local_name,
                database_name=table_obj.database_name,
                folder_name=table_obj.folder_name,
                table_name=table_obj.table_name,
                columns=table_obj.columns,
            )

            self.db_session.delete(table_obj)
            self.db_session.commit()
            self.db_session.add(new_table_obj)
            self.db_session.commit()

            # Replace name in granter_tables fields in user and admin tokens after rename
            for token in (
                self.get_user_tokens_objects_list()
                + self.get_admin_tokens_objects_list()
            ):
                if old_local_name in token.granted_tables:
                    token.granted_tables = [
                        new_local_name if i == old_local_name else i
                        for i in token.granted_tables
                    ]

        self.db_session.commit()
