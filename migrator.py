"""
| A python file that manages all CRUD operations for the database. Here I will
| handle data insertion logic.
"""

import sqlite3
import csv

def add_store(conn, store):
    '''
    Function that adds store into the database.
    Returns the last row id of all inserted 'stores'.
    '''

    sql =   """
            INSERT INTO store(name)
            VALUES(?)
            """
    cursor = conn.cursor()

    # execute insert statement
    cursor.execute(sql, store)
    conn.commit()

    # return last row's ID
    return cursor.lastrowid

def add_item(conn, item):
    '''
    Function that adds items into the database.
    Returns the last row id of all inserted 'items'.
    '''

    sql =   """
            INSERT INTO item(store,name,unitCost,weightKg)
            VALUES(?,?,?,?)
            """
    cursor = conn.cursor()

    # execute insert statement
    cursor.execute(sql, item)
    conn.commit()

    # return last row's ID
    return cursor.lastrowid

def add_address(conn, address):
    '''
    Function that adds addresses into the database.
    Returns the last row id of all inserted 'addresses'.
    '''

    sql =   """
            INSERT INTO address(store,line)
            VALUES(?,?)
            """
    cursor = conn.cursor()

    # execute insert statement
    cursor.execute(sql, address)
    conn.commit()

    # return last row's ID
    return cursor.lastrowid


# Main function tbc