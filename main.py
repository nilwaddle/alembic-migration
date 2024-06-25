from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from typing import List, Dict, Optional, Union
from filelock import FileLock
import ast

# import models
from pydantic import BaseModel, field_validator, Field
import re
import os
import importlib

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Configure Alembic
alembic_cfg = Config("alembic.ini")
script = ScriptDirectory.from_config(alembic_cfg)
versions_dir = alembic_cfg.get_main_option("version_locations", "alembic/versions")


class RevisionDetails(BaseModel):
    revision_id: str
    parent: Optional[str]
    path: str
    message: str
    create_date: str


class ColumnDefinition(BaseModel):
    name: str
    type: str

    attributes: Optional[str] = Field(
        None,
        description="Additional SQLAlchemy column attributes, e.g., 'primary_key=True, nullable=False'",
    )

    @field_validator("name", mode="before")
    def validate_name(cls, v: str) -> str:
        v = v.strip().replace(" ", "").lower()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            raise ValueError(
                "Column name must start with a letter or underscore, followed by letters, digits, or underscores."
            )
        return v

    @field_validator("type", mode="before")
    def validate_type(cls, v: str) -> str:
        allowed_types = ["Integer", "String", "Float", "Boolean", "Date", "Text"]
        v = v.strip().split(",")[0].capitalize()  # Only take the type, capitalize it
        if v not in allowed_types:
            raise ValueError(
                f"Invalid type '{v}'. Allowed types are: {', '.join(allowed_types)}"
            )
        return v

    @field_validator("attributes", mode="before")
    def validate_attributes(cls, v: Optional[Union[str, List[str]]]) -> Optional[str]:
        allowed_attributes = {
            "primary_key",
            "nullable",
            "unique",
            "index",
            "default",
            "server_default",
            "autoincrement",
            "foreign_key",
            "comment",
            "",
        }
        if isinstance(v, list):
            v = ", ".join(map(str, v))

        if isinstance(v, str):
            attr_parts = [part.strip() for part in v.split(",")]
            for part in attr_parts:
                key_value = part.split("=")
                key = key_value[0].strip()

                if key not in allowed_attributes:
                    raise ValueError(
                        f"Invalid attribute '{key}'. Allowed attributes are: {', '.join(allowed_attributes)}"
                    )

            return ", ".join(attr_parts)

        raise ValueError("Attributes must be a string or list of strings.")


class CreateTableRequest(BaseModel):
    table_name: str
    columns: List[ColumnDefinition]

    @field_validator("table_name", mode="before")
    def validate_table_name(cls, v: str) -> str:
        v = v.strip().replace(" ", "_").capitalize()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            raise ValueError(
                "Table name must start with a letter or underscore, followed by letters, digits, or underscores."
            )
        return v

    @field_validator("columns", mode="after")
    def ensure_primary_key(cls, v: List[ColumnDefinition]) -> List[ColumnDefinition]:
        if not any("primary_key=True" in (col.attributes or "") for col in v):
            raise ValueError("At least one column must be defined as the primary key.")
        return v


def validate_sql_identifier(value: str) -> str:
    value = value.lower().replace(" ", "")
    if not re.match(r"^[a-z_][a-z0-9_]*$", value):
        raise ValueError(
            "Identifier must start with a letter or underscore, followed by letters, digits, or underscores."
        )
    return value


class ColumneditDefinition(BaseModel):
    name: str
    type: Optional[str]
    attributes: Optional[str] = Field(
        None,
        description="Additional SQLAlchemy column attributes, e.g., 'primary_key=True, nullable=False'",
    )

    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        return validate_sql_identifier(v)

    @field_validator("type")
    def validate_type(cls, v: str) -> str:
        allowed_types = [
            "Integer",
            "String",
            "Float",
            "Boolean",
            "Date",
            "Text",
        ]
        v = v.strip().capitalize()  # Only take the type, capitalize it
        if v not in allowed_types:
            raise ValueError(
                f"Invalid type '{v}'. Allowed types are: {', '.join(allowed_types)}"
            )
        return v

    @field_validator("attributes")
    def validate_attributes(cls, v: Optional[str]) -> Optional[str]:
        if v:
            attr_parts = [part.strip() for part in v.split(",")]
            for part in attr_parts:
                if not re.match(r"^\w+\s*=\s*.+$", part):
                    raise ValueError(
                        f"Invalid attribute format: '{part}'. Expected format is 'key=value'."
                    )
            return ", ".join(attr_parts)
        return v


class EditColumnRequest(BaseModel):
    name: str
    new_name: Optional[str] = None
    new_type: Optional[str] = None
    new_attributes: Optional[str] = None

    @field_validator("name", "new_name")
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return validate_sql_identifier(v)
        return v

    @field_validator("new_type")
    def validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v:
            allowed_types = [
                "Integer",
                "String",
                "Float",
                "Boolean",
                "Date",
                "Text",
            ]
            v = v.strip().capitalize()
            if v not in allowed_types:
                raise ValueError(
                    f"Invalid type '{v}'. Allowed types are: {', '.join(allowed_types)}"
                )
            return v
        return v

    @field_validator("new_attributes")
    def validate_attributes(cls, v: Optional[str]) -> Optional[str]:
        if v:
            attr_parts = [part.strip() for part in v.split(",")]
            for part in attr_parts:
                if not re.match(r"^\w+\s*=\s*.+$", part):
                    raise ValueError(
                        f"Invalid attribute format: '{part}'. Expected format is 'key=value'."
                    )
            return ", ".join(attr_parts)
        return v


class EditTableRequest(BaseModel):
    table_name: str
    add_columns: Optional[List[ColumneditDefinition]]
    delete_columns: Optional[List[str]]
    edit_columns: Optional[List[EditColumnRequest]]

    @field_validator("table_name")
    def validate_table_name(cls, v: str) -> str:
        return v.capitalize()


class RenameTableRequest(BaseModel):
    old_name: str
    new_name: str

    @field_validator("old_name", "new_name", mode="before")
    def validate_table_names(cls, v: str) -> str:
        v = v.strip().replace(" ", "_").capitalize()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
            raise ValueError(
                "Table name must start with a letter or underscore, followed by letters, digits, or underscores."
            )
        return v


class DeleteTableRequest(BaseModel):
    table_name: str

    @field_validator("table_name")
    def validate_table_name(cls, v: str) -> str:
        return v.capitalize()


# models.Base.metadata.create_all(models.engine)


def run_migrations(command_type: str, revision: str = "head"):
    try:
        if command_type == "upgrade":
            command.upgrade(alembic_cfg, revision)
        elif command_type == "downgrade":
            command.downgrade(alembic_cfg, revision)
        else:
            raise ValueError("Invalid command type")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/migrate/generate_migration")
def generate_migration(message: str = "autogenerated migration"):
    """
    Generate a new migration script automatically.

    This endpoint allows generating a new migration script automatically using Alembic's autogenerate feature.
    The generated migration script includes changes detected by comparing the current database state with the
    models defined in the application.

    Args:
        message (str, optional): A descriptive message for the migration script.
                                 Defaults to "autogenerated migration" if not provided.

    Returns:
        dict: JSON response indicating the result of the migration script generation.
              The response includes a detail message confirming the success or failure of the operation.
    """
    try:
        sanitized_message = re.sub(r"[^a-zA-Z0-9_-]", "_", message)
        command.revision(alembic_cfg, message=sanitized_message, autogenerate=True)
        return {"detail": "Migration script generated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def reload_models():
    try:
        import models

        importlib.reload(models)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reloading models: {str(e)}")


# Pydantic models
# class ColumnDefinition(BaseModel):
#     name: str
#     type: str
#     collation: Optional[str] = None
#     nullable: bool = True
#     default: Optional[Union[str, int, float, bool]] = None
#     primary_key: bool = False

#     @property
#     def sqlalchemy_attributes(self) -> str:
#         attributes: List[str] = []
#         if self.collation:
#             attributes.append(f"collation='{self.collation}'")
#         if not self.nullable:
#             attributes.append("nullable=False")
#         if self.default is not None:
#             default_value = self.default
#             if isinstance(default_value, str):
#                 default_value = f"'{default_value}'"
#             attributes.append(f"default={default_value}")
#         if self.primary_key:
#             attributes.append("primary_key=True")

#         return ", ".join(attributes)

#     @property
#     def sqlalchemy_column_declaration(self) -> str:
#         attributes = self.sqlalchemy_attributes
#         if attributes:
#             return f"Column({self.type}, {attributes})"
#         else:
#             return f"Column({self.type})"

#     @field_validator("name")
#     def validate_name(cls, v: str) -> str:
#         v = v.strip().replace(" ", "").lower()
#         if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
#             raise ValueError(
#                 "Column name must start with a letter or underscore, followed by letters, digits, or underscores."
#             )
#         return v

#     @field_validator("type")
#     def validate_type(cls, v: str) -> str:
#         allowed_types = ["Integer", "String", "Float", "Boolean", "Date", "Text"]
#         v = v.strip().split(",")[0].capitalize()  # Only take the type, capitalize it
#         if v not in allowed_types:
#             raise ValueError(
#                 f"Invalid type '{v}'. Allowed types are: {', '.join(allowed_types)}"
#             )
#         return v


# class CreateTableRequest(BaseModel):
#     table_name: str
#     columns: List[ColumnDefinition]

#     @field_validator("table_name")
#     def validate_table_name(cls, v: str) -> str:
#         v = v.strip().replace(" ", "_").capitalize()
#         if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", v):
#             raise ValueError(
#                 "Table name must start with a letter or underscore, followed by letters, digits, or underscores."
#             )
#         return v

#     @field_validator("columns")
#     def ensure_primary_key(cls, v: List[ColumnDefinition]) -> List[ColumnDefinition]:
#         if not any(col.primary_key for col in v):
#             raise ValueError("At least one column must be defined as the primary key.")
#         return v


# # Function to add the table to models.py
# def add_table_to_models(
#     file_path: str,
#     table_name: str,
#     columns: List[Dict[str, Union[str, int, float, bool, None]]],
# ):
#     with open(file_path, "r") as file:
#         lines = file.readlines()

#     # Check if the table already exists
#     for line in lines:
#         if f"class {table_name}" in line:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Table {table_name} already exists in models.py",
#             )

#     new_table_lines = [f"\n\nclass {table_name}(Base):\n"]
#     new_table_lines.append(f"    __tablename__ = '{table_name.lower()}'\n")
#     for column in columns:
#         col_name = column["name"]
#         col_type = column["type"]
#         col_attributes: List[str] = []

#         # Handle primary key
#         if column.get("primary_key", False):
#             col_attributes.append("primary_key=True")
#         # Handle nullable
#         if not column.get("nullable", True):
#             col_attributes.append("nullable=False")
#         # Handle default
#         if column.get("default") is not None:
#             default_value = column["default"]
#             if isinstance(default_value, str):
#                 default_value = f"'{default_value}'"
#             col_attributes.append(f"default={default_value}")

#         # Construct the column definition string
#         attributes_str = ", ".join(col_attributes)
#         if attributes_str:
#             new_table_lines.append(
#                 f"    {col_name} = Column({col_type}, {attributes_str})\n"
#             )
#         else:
#             new_table_lines.append(f"    {col_name} = Column({col_type})\n")

#         # Add collation as a comment if provided, for documentation purposes
#         if column.get("collation"):
#             new_table_lines.append(
#                 f"    # Collation for {col_name}: {column['collation']}\n"
#             )

#     lines.extend(new_table_lines)

#     with open(file_path, "w") as file:
#         file.writelines(lines)
#     reload_models()


# @app.post("/add_table")
# def create_table(request: CreateTableRequest):
#     """
#     Add a new table definition to the models.py file.

#     This endpoint allows adding a new table definition to the `models.py` file,
#     specifying the table name and its columns, ensuring at least one column is
#     designated as the primary key.

#     Args:
#         request (CreateTableRequest): A request body containing the details of the table to be added.

#     Returns:
#         dict: JSON response indicating the result of adding the table to the models.py file.
#               The response includes a detail message confirming the success or failure of the operation.
#     """
#     models_path = "/app/models.py"  # Adjust as per your actual path
#     try:
#         # Acquire a file lock
#         with FileLock(models_path + ".lock"):  # Locking on models.py file
#             add_table_to_models(
#                 models_path,
#                 request.table_name,
#                 [
#                     {
#                         "name": col.name,
#                         "type": col.type,
#                         "primary_key": col.primary_key,
#                         "nullable": col.nullable,
#                         "default": col.default,
#                         "collation": col.collation,
#                     }
#                     for col in request.columns
#                 ],
#             )

#         generate_migration(message=f"Add table {request.table_name}")
#         run_migrations("upgrade")
#         reload_models()
#         tables = parse_models_file(models_path)
#         return {
#             "detail": f"Table '{request.table_name}' added to models.py.",
#             "tables": tables,
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.post("/add_table")
def create_table(request: CreateTableRequest):
    """
    Add a new table definition to the models.py file.

    This endpoint allows adding a new table definition to the `models.py` file,
    specifying the table name and its columns, ensuring at least one column is
    designated as the primary key.

    Args:
        request (CreateTableRequest): A request body containing the details of the table to be added.

    Returns:
        dict: JSON response indicating the result of adding the table to the models.py file.
              The response includes a detail message confirming the success or failure of the operation.
    """
    models_path = "/app/models.py"
    try:
        # Acquire a file lock
        with FileLock(models_path + ".lock"):  # Locking on models.py file
            add_table_to_models(
                models_path,
                request.table_name,
                [
                    {
                        "name": col.name,
                        "type": col.type,
                        "attributes": col.attributes or "",
                    }
                    for col in request.columns
                ],
            )
            # Command to upgrade the database after modifying models.py

        run_migrations("upgrade")
        generate_migration(message=f"Add table {request.table_name}")
        run_migrations("upgrade")
        reload_models()
        tables = parse_models_file(models_path)
        return {
            "detail": f"Table '{request.table_name}' added to models.py.",
            "tables": tables,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Function to add the table to models.py
def add_table_to_models(file_path: str, table_name: str, columns: List[Dict[str, str]]):
    with open(file_path, "r") as file:
        lines = file.readlines()

    # Check if the table already exists
    for line in lines:
        if f"class {table_name}" in line:
            raise HTTPException(
                status_code=400,
                detail=f"Table {table_name} already exists in models.py",
            )

    new_table_lines = [f"\n\nclass {table_name}(Base):\n"]
    new_table_lines.append(f"    __tablename__ = '{table_name.lower()}'\n")
    for column in columns:
        attr_str = f", {column['attributes']}" if column["attributes"] else ""
        new_table_lines.append(
            f"    {column['name']} = Column({column['type']}{attr_str})\n"
        )

    lines.extend(new_table_lines)

    with open(file_path, "w") as file:
        file.writelines(lines)
    reload_models()


# def edit_table_in_models(
#     file_path: str,
#     table_name: str,
#     add_columns: List[Dict[str, str]],
#     edit_columns: List[Dict[str, str]],
#     delete_columns: List[str],
# ) -> None:
#     # Check if the file exists and is writable
#     lock = FileLock(f"{file_path}.lock")
#     with lock:

#         if not os.path.exists(file_path):
#             raise HTTPException(
#                 status_code=404, detail=f"File {file_path} does not exist."
#             )
#         if not os.access(file_path, os.W_OK):
#             raise HTTPException(
#                 status_code=403, detail=f"File {file_path} is not writable."
#             )

#         with open(file_path, "r") as file:
#             lines = file.readlines()

#         model_start = None
#         model_end = None

#         # Find the start and end of the model class definition
#         for i, line in enumerate(lines):
#             if f"class {table_name}" in line:
#                 model_start = i
#                 print(f"Found start of class {table_name} at line {model_start}")
#             if model_start is not None and line.strip() == "":
#                 model_end = i
#                 break

#         if model_start is None:
#             raise HTTPException(
#                 status_code=404, detail=f"Table {table_name} not found in models.py"
#             )

#         # If no empty line is found, set model_end to the length of lines (i.e., the end of the file)
#         if model_end is None:
#             model_end = len(lines)
#         print(f"Model class ends at line {model_end}")

#         # Remove existing columns that are to be deleted
#         # if delete_columns:
#         #     for i in range(model_start, model_end):
#         #         line = lines[i].strip()
#         #         for col in delete_columns:
#         #             if line.startswith(f"{col} = Column("):
#         #                 lines[i] = f"# Deleted column: {line}\n"
#         #                 print(f"Deleted column: {col}")
#         # Remove existing columns that are to be deleted
#         if delete_columns:
#             # Use a list comprehension to filter out lines that should be deleted
#             lines = [
#                 line
#                 for i, line in enumerate(lines)
#                 if not any(
#                     line.strip().startswith(f"{col} = Column(")
#                     for col in delete_columns
#                 )
#                 or i < model_start
#                 or i >= model_end
#             ]
#             print(f"Deleted columns: {delete_columns}")
#         # Add new columns
#         if add_columns:
#             insert_position = model_end - 1
#             for col in add_columns:
#                 new_column_line = f"    {col['name']} = Column({col['type']}"
#                 if col["attributes"]:
#                     new_column_line += f", {col['attributes']}"
#                 new_column_line += ")\n"
#                 lines.insert(insert_position, new_column_line)
#                 insert_position += 1
#                 print(f"Added new column: {new_column_line.strip()}")

#         # Edit existing columns
#         for col in edit_columns:
#             if "name" not in col:
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"Missing required fields in edit_columns: {col}",
#                 )

#             found = False
#             for i in range(model_start, model_end):
#                 line = lines[i].strip()
#                 if line.startswith(f"{col['name']} = Column("):
#                     # Extract existing type and attributes
#                     current_attributes = line.split("(", 1)[1].rsplit(")", 1)[0]
#                     existing_type_and_attrs = current_attributes.split(",", 1)

#                     existing_type = existing_type_and_attrs[0].strip()
#                     if len(existing_type_and_attrs) == 2:
#                         existing_attrs = existing_type_and_attrs[1]
#                     else:
#                         existing_attrs = ""

#                     existing_attrs_list = [
#                         attr.strip()
#                         for attr in existing_attrs.split(",")
#                         if attr.strip()
#                     ]
#                     new_attrs_list = [
#                         attr.strip()
#                         for attr in (col.get("new_attributes") or "").split(",")
#                         if attr.strip()
#                     ]

#                     # Combine existing and new attributes
#                     combined_attrs_set = set(existing_attrs_list).union(new_attrs_list)
#                     combined_attrs = ", ".join(combined_attrs_set)

#                     # Use existing type if new_type is not provided
#                     final_type = col.get("new_type", existing_type)

#                     # Construct the new column line
#                     new_column_line = f"    {col['new_name'] if 'new_name' in col and col['new_name'] else col['name']} = Column({final_type}"
#                     if combined_attrs:
#                         new_column_line += f", {combined_attrs}"
#                     new_column_line += ")\n"

#                     lines[i] = new_column_line
#                     found = True
#                     print(f"Edited column: {new_column_line.strip()}")
#                     break

#             if not found:
#                 raise HTTPException(
#                     status_code=404,
#                     detail=f"Column {col['name']} not found in table {table_name}",
#                 )

#     # Print the final lines before writing to verify changes
#     print("Final lines to write:")
#     for line in lines:
#         print(line.strip())

#     temp_file_path = f"{file_path}.tmp"
#     with open(temp_file_path, "w") as temp_file:
#         temp_file.writelines(lines)
#     os.replace(temp_file_path, file_path)
#     # with open(file_path, "w") as file:
#     #     file.writelines(lines)
#     print(f"Successfully wrote changes to {file_path}")
#     reload_models()


def edit_table_in_models(
    file_path: str,
    table_name: str,
    add_columns: List[Dict[str, str]],
    edit_columns: List[Dict[str, str]],
    delete_columns: List[str],
) -> None:
    # Check if the file exists and is writable
    lock = FileLock(f"{file_path}.lock")
    with lock:

        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404, detail=f"File {file_path} does not exist."
            )
        if not os.access(file_path, os.W_OK):
            raise HTTPException(
                status_code=403, detail=f"File {file_path} is not writable."
            )

        with open(file_path, "r") as file:
            lines = file.readlines()

        model_start = None
        model_end = None

        # Find the start and end of the model class definition
        for i, line in enumerate(lines):
            if f"class {table_name}" in line:
                model_start = i
                print(f"Found start of class {table_name} at line {model_start}")
            if model_start is not None and line.strip() == "":
                model_end = i
                break

        if model_start is None:
            raise HTTPException(
                status_code=404, detail=f"Table {table_name} not found in models.py"
            )

        # If no empty line is found, set model_end to the length of lines (i.e., the end of the file)
        if model_end is None:
            model_end = len(lines)
        print(f"Model class ends at line {model_end}")

        # Verify that no primary key column is in delete_columns
        primary_keys: List[str] = []
        for i in range(model_start, model_end):
            line = lines[i].strip()
            for col in delete_columns:
                if line.startswith(f"{col} = Column(") and "primary_key=True" in line:
                    primary_keys.append(col)

        if primary_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete primary key column(s): {', '.join(primary_keys)}",
            )

        # Remove existing columns that are to be deleted
        if delete_columns:
            # Use a list comprehension to filter out lines that should be deleted
            lines = [
                line
                for i, line in enumerate(lines)
                if not any(
                    line.strip().startswith(f"{col} = Column(")
                    for col in delete_columns
                )
                or i < model_start
                or i >= model_end
            ]
            print(f"Deleted columns: {delete_columns}")

        # Add new columns
        if add_columns:
            insert_position = model_end - 1
            for col in add_columns:
                new_column_line = f"    {col['name']} = Column({col['type']}"
                if col["attributes"]:
                    new_column_line += f", {col['attributes']}"
                new_column_line += ")\n"
                lines.insert(insert_position, new_column_line)
                insert_position += 1
                print(f"Added new column: {new_column_line.strip()}")

        # Edit existing columns
        for col in edit_columns:
            if "name" not in col:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required fields in edit_columns: {col}",
                )

            found = False
            for i in range(model_start, model_end):
                line = lines[i].strip()
                if line.startswith(f"{col['name']} = Column("):
                    # Extract existing type and attributes
                    current_attributes = line.split("(", 1)[1].rsplit(")", 1)[0]
                    existing_type_and_attrs = current_attributes.split(",", 1)

                    existing_type = existing_type_and_attrs[0].strip()
                    if len(existing_type_and_attrs) == 2:
                        existing_attrs = existing_type_and_attrs[1]
                    else:
                        existing_attrs = ""

                    existing_attrs_list = [
                        attr.strip()
                        for attr in existing_attrs.split(",")
                        if attr.strip()
                    ]
                    new_attrs_list = [
                        attr.strip()
                        for attr in (col.get("new_attributes") or "").split(",")
                        if attr.strip()
                    ]

                    # Combine existing and new attributes
                    combined_attrs_set = set(existing_attrs_list).union(new_attrs_list)
                    combined_attrs = ", ".join(combined_attrs_set)

                    # Use existing type if new_type is not provided
                    final_type = col.get("new_type", existing_type)

                    # Construct the new column line
                    new_column_line = f"    {col['new_name'] if 'new_name' in col and col['new_name'] else col['name']} = Column({final_type}"
                    if combined_attrs:
                        new_column_line += f", {combined_attrs}"
                    new_column_line += ")\n"

                    lines[i] = new_column_line
                    found = True
                    print(f"Edited column: {new_column_line.strip()}")
                    break

            if not found:
                raise HTTPException(
                    status_code=404,
                    detail=f"Column {col['name']} not found in table {table_name}",
                )

    # Print the final lines before writing to verify changes
    print("Final lines to write:")
    for line in lines:
        print(line.strip())

    temp_file_path = f"{file_path}.tmp"
    with open(temp_file_path, "w") as temp_file:
        temp_file.writelines(lines)
    os.replace(temp_file_path, file_path)
    print(f"Successfully wrote changes to {file_path}")
    reload_models()


@app.post("/migrate/edit_table")
def edit_table(request: EditTableRequest):
    try:
        models_path = "/app/models.py"

        # Prepare the edit_columns list
        if request.edit_columns is not None:
            edit_columns = [
                {
                    "name": col.name,
                    "new_name": col.new_name,
                    "new_type": col.new_type,
                    "new_attributes": col.new_attributes,
                }
                for col in request.edit_columns
                if col.name  # Allow edits even if new_type or new_attributes are None
            ]
            # Filter out None values from the dictionaries
            edit_columns = [
                {k: v for k, v in col.items() if v is not None} for col in edit_columns
            ]
        else:
            edit_columns = []

        # Prepare the add_columns list
        if request.add_columns is not None:
            add_columns = [
                {
                    "name": col.name,
                    "type": col.type,
                    "attributes": col.attributes if col.attributes else "",
                }
                for col in request.add_columns
                if col.name and col.type
            ]
        else:
            add_columns = []

        # Prepare the delete_columns list
        if request.delete_columns is not None:
            delete_columns = [col for col in request.delete_columns if col]
        else:
            delete_columns = []

        # Call edit_table_in_models with the filtered lists
        edit_table_in_models(
            models_path, request.table_name, add_columns, edit_columns, delete_columns
        )
        generate_migration(message=f"Edited table {request.table_name}")
        run_migrations("upgrade")
        reload_models()
        tables = parse_models_file(models_path)
        return {
            "detail": f"Table '{request.table_name}' edited successfully in models.py.",
            "tables": tables,
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/migrate/edit_table")
# def edit_table(request: EditTableRequest):
#     try:
#         models_path = "/app/models.py"

#         # Prepare the edit_columns list
#         if request.edit_columns is not None:
#             edit_columns = [
#                 {
#                     "name": col.name,
#                     "new_name": col.new_name,
#                     "new_type": col.new_type,
#                     "new_attributes": col.new_attributes,
#                 }
#                 for col in request.edit_columns
#                 if col.name  # Allow edits even if new_type or new_attributes are None
#             ]
#             # Filter out None values from the dictionaries
#             edit_columns = [
#                 {k: v for k, v in col.items() if v is not None} for col in edit_columns
#             ]
#         else:
#             edit_columns = []

#         # Prepare the add_columns list
#         if request.add_columns is not None:
#             add_columns = [
#                 {
#                     "name": col.name,
#                     "type": col.type,
#                     "attributes": col.attributes if col.attributes else "",
#                 }
#                 for col in request.add_columns
#                 if col.name and col.type
#             ]
#         else:
#             add_columns = []

#         # Prepare the delete_columns list
#         if request.delete_columns is not None:
#             delete_columns = [col for col in request.delete_columns if col]
#         else:
#             delete_columns = []

#         # Call edit_table_in_models with the filtered lists
#         edit_table_in_models(
#             models_path, request.table_name, add_columns, edit_columns, delete_columns
#         )
#         run_migrations("upgrade")
#         generate_migration(message=f"Edited table {request.table_name}")
#         run_migrations("upgrade")
#         reload_models()
#         tables = parse_models_file(models_path)
#         return {
#             "detail": f"Table '{request.table_name}' edited successfully in models.py.",
#             "tables": tables,
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@app.post("/migrate/upgrade/{revision}")
def upgrade_migration(revision: str = "head"):
    """
    Upgrade the database to a specified revision.

    Args:
        revision (str): The target revision to upgrade to. Defaults to 'head'.
                        Options include:
                        - 'head': Upgrade to the latest revision.
                        - Specific revision ID: Upgrade to a specific revision.
                        - Step count (e.g., '+1', '+2'): Move forward by the specified number of revisions.

    Returns:
        dict: JSON response indicating the result of the upgrade operation.

    """
    run_migrations("upgrade", revision)
    return {"detail": f"Upgraded to revision {revision} successfully"}


@app.post("/migrate/downgrade")
def downgrade_migration(revision: Optional[str] = "-1"):
    """
    Downgrade the database to a specified revision.

    Args:
        revision (Optional[str]): The revision to downgrade to. Can be a specific revision ID,
                                  '-1' for the previous revision, '-2' for two revisions back, etc.
                                  Defaults to '-1' if no specific revision is provided.

    Returns:
        JSON response indicating the result of the downgrade.
    """
    target_revision = revision if revision is not None else "-1"
    run_migrations("downgrade", target_revision)
    return {"detail": f"Downgraded to revision {target_revision} successfully"}


@app.get("/migrate/head")
def get_head() -> Dict[str, List[str]]:
    try:
        heads = script.get_heads()
        return {"heads": heads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def extract_creation_date(file_path: str) -> str:
    try:
        with open(file_path, "r") as file:
            content = file.read()
            match = re.search(r"Create Date:\s+([\d\-:\.\s]+)", content)
            if match:
                return match.group(1).strip()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
    return ""


@app.get("/migrate/revisions", response_model=List[RevisionDetails])
def get_revision_details() -> List[RevisionDetails]:
    """
    Retrieve details of all revisions available in the Alembic migration script.

    This endpoint collects details of all revisions available in the Alembic migration script
    and returns them in the form of a list of `RevisionDetails` objects.

    Returns:
        List[RevisionDetails]: A list containing details of all revisions available in the migration script.
                               Each item in the list represents a single revision and includes attributes
                               such as revision ID, parent revision(s), file path, message, and creation date.
    """
    try:

        # Collect revision details
        revisions: List[RevisionDetails] = []
        for rev in script.walk_revisions():
            script_path = os.path.join(script.versions, rev.path)
            # Extract the parent revision(s)
            if rev.down_revision:
                if isinstance(rev.down_revision, tuple):
                    parent_revision = ", ".join(rev.down_revision)
                else:
                    parent_revision = rev.down_revision
            else:
                parent_revision = None
            # Convert parent_revision to string if it's a list (safety check)
            if isinstance(parent_revision, list):
                parent_revision = ", ".join(parent_revision)

            create_date = extract_creation_date(script_path)

            # Append the revision details to the list
            revisions.append(
                RevisionDetails(
                    revision_id=rev.revision,
                    parent=parent_revision,
                    path=script_path,
                    message=rev.doc or "",
                    create_date=create_date,
                )
            )

        return revisions

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/migrate/rename_table")
def rename_table(request: RenameTableRequest):
    """
    Rename an existing table in the models.py file.

    Args:
        request (RenameTableRequest): A request body containing the old and new table names.

    Returns:
        dict: JSON response indicating the result of renaming the table in the models.py file.
              The response includes a detail message confirming the success or failure of the operation.
    """
    try:
        models_path = "/app/models.py"
        rename_table_in_models(models_path, request.old_name, request.new_name)
        run_migrations("upgrade")
        generate_migration(
            message=f"renamed table {request.old_name} to {request.new_name}"
        )
        run_migrations("upgrade")
        return {
            "detail": f"Table '{request.old_name}' renamed to '{request.new_name}' in models.py."
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def rename_table_in_models(file_path: str, old_name: str, new_name: str):
    lock = FileLock(f"{file_path}.lock")
    with lock:
        with open(file_path, "r") as file:
            lines = file.readlines()

        class_pattern = re.compile(rf"class\s+{old_name}\s*\(.*\):")
        tablename_pattern = re.compile(rf"__tablename__\s*=\s*'{old_name.lower()}'")

        class_renamed = False
        tablename_renamed = False

        for i, line in enumerate(lines):
            if class_pattern.match(line):
                lines[i] = line.replace(old_name, new_name)
                class_renamed = True
            if tablename_pattern.search(line):
                lines[i] = line.replace(old_name.lower(), new_name.lower())
                tablename_renamed = True

        if not (class_renamed and tablename_renamed):
            raise ValueError(f"Table '{old_name}' not found in models.py")

        with open(file_path, "w") as file:
            file.writelines(lines)


@app.get(
    "/migrate/show_tables",
    response_model=List[Dict[str, Union[str, List[Dict[str, str]]]]],
)
def get_tables_from_models():
    """
    Get all tables and their columns from the models.py file.

    This endpoint parses the models.py file to extract information about the tables and their columns.
    The response includes table names and details of each column, such as name, type, and attributes.

    Returns:
        List[dict]: JSON response containing the list of tables and their column details.
    """
    models_file_path = (
        "/app/models.py"  # Adjust this path to your actual models.py file location
    )
    if not os.path.exists(models_file_path):
        raise HTTPException(status_code=404, detail="models.py file not found")

    try:
        tables = parse_models_file(models_file_path)
        return tables
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def parse_models_file(
    models_file_path: str,
) -> List[Dict[str, Union[str, List[Dict[str, str]]]]]:
    tables: List[Dict[str, Union[str, List[Dict[str, str]]]]] = []

    with open(models_file_path, "r") as file:
        tree = ast.parse(file.read(), filename=models_file_path)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):  # Identify class definitions
            table_name: str = node.name.lower()  # Convert table name to lowercase
            columns: List[Dict[str, str]] = []

            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and isinstance(
                    stmt.targets[0], ast.Name
                ):
                    col_name: str = stmt.targets[0].id

                    if col_name == "__tablename__":
                        # Skip the __tablename__ attribute
                        continue

                    if isinstance(stmt.value, ast.Call):
                        # Extract column type
                        if isinstance(stmt.value.func, ast.Name):
                            col_type: str = stmt.value.func.id
                        elif isinstance(stmt.value.func, ast.Attribute):
                            col_type: str = stmt.value.func.attr
                        else:
                            col_type: str = "UnknownType"

                        # Special case: Convert "Column" to actual column type if possible
                        if col_type == "Column":
                            for arg in stmt.value.args:
                                if isinstance(arg, ast.Name):
                                    col_type = arg.id
                                    break

                        # Extract attributes
                        col_attributes: List[str] = []
                        for kw in stmt.value.keywords:
                            if isinstance(kw.value, ast.Constant):
                                col_value = kw.value.s
                            elif isinstance(kw.value, ast.Name):
                                col_value = kw.value.id
                            else:
                                col_value = ast.dump(
                                    kw.value
                                )  # Fallback for complex types

                            col_attributes.append(f"{kw.arg}={col_value}")

                        columns.append(
                            {
                                "name": col_name,
                                "type": col_type,
                                "attributes": ", ".join(col_attributes),
                            }
                        )

                    else:
                        columns.append(
                            {"name": col_name, "type": "UnknownType", "attributes": ""}
                        )

            tables.append({"table_name": table_name, "columns": columns})
    reload_models()
    return tables


def delete_table_from_models(file_path: str, table_name: str) -> None:
    # Check if the file exists and is writable
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File {file_path} does not exist.")
    if not os.access(file_path, os.W_OK):
        raise HTTPException(
            status_code=403, detail=f"File {file_path} is not writable."
        )

    with open(file_path, "r") as file:
        lines = file.readlines()

    model_start = None
    model_end = None

    # Find the start and end of the model class definition
    for i, line in enumerate(lines):
        if f"class {table_name}" in line:
            model_start = i
            print(f"Found start of class {table_name} at line {model_start}")
        if model_start is not None and line.strip() == "":
            model_end = i
            break

    if model_start is None:
        raise HTTPException(
            status_code=404, detail=f"Table {table_name} not found in models.py"
        )

    # If no empty line is found after the start, set model_end to the length of lines (i.e., the end of the file)
    if model_end is None:
        model_end = len(lines)

    # Remove the lines corresponding to the table class definition
    del lines[model_start : model_end + 1]

    # Print the final lines before writing to verify changes
    print("Final lines to write after deletion:")
    for line in lines:
        print(line.strip())

    with open(file_path, "w") as file:
        file.writelines(lines)
    print(f"Successfully removed table '{table_name}' from {file_path}")


@app.post("/migrate/delete_table")
def delete_table(request: DeleteTableRequest):
    try:
        models_path = "/app/models.py"  # Path to your models.py file

        # Call the function to delete the table
        delete_table_from_models(models_path, request.table_name)
        run_migrations("upgrade")
        generate_migration(message=f"Deleted table {request.table_name}")
        run_migrations("upgrade")
        return {
            "detail": f"Table '{request.table_name}' deleted successfully from models.py."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
