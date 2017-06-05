"""SCRIPT SERVICE"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import datetime
import logging
import base64
import json
from uuid import UUID

from gefapi import db
from gefapi.models import Execution, ExecutionLog
from gefapi.services import ScriptService, docker_run
from gefapi.config import SETTINGS
from gefapi.errors import ExecutionNotFound, ScriptNotFound, ScriptStateNotValid


def dict_to_query(params):
    query = ''
    for key in params.keys():
        query += key+'='+params.get(key)+'&'
    return query[0:-1]


class ExecutionService(object):
    """Execution Class"""


    @staticmethod
    def get_executions(user):
        logging.info('[SERVICE]: Getting executions')
        logging.info('[DB]: QUERY')
        if user.role == 'ADMIN':
            executions = Execution.query.all()
            return executions
        else:
            executions = db.session.query(Execution) \
                .filter(Execution.user_id == user.id)
            return executions

    @staticmethod
    def create_execution(script_id, params, user):
        logging.info('[SERVICE]: Creating execution')
        script = ScriptService.get_script(script_id, user)
        if not script:
            raise ScriptNotFound(message='Script with id '+script_id+' does not exist')
        if script.status != 'SUCCESS':
            raise ScriptStateNotValid(message='Script with id '+script_id+' is not BUILT')
        execution = Execution(script_id=script.id, params=params, user_id=user.id)
        try:
            logging.info('[DB]: ADD')
            db.session.add(execution)
            db.session.commit()
        except Exception as error:
            raise error

        try:
            environment = SETTINGS.get('environment', {})
            environment['EXECUTION_ID'] = execution.id
            param_serial = json.dumps(params).encode('utf-8')
            param_serial = str(base64.b64encode(param_serial)).replace('\'', '')
            logging.debug(param_serial)
            docker_run.delay(execution.id, script.slug, environment, param_serial)
        except Exception as e:
            raise e
        return execution

    @staticmethod
    def get_execution(execution_id, user='fromservice'):
        logging.info('[SERVICE]: Getting execution '+execution_id)
        logging.info('[DB]: QUERY')
        # user = 'from service' just in case the requests comes from the service
        if user == 'fromservice' or user.role == 'ADMIN':
            try:
                val = UUID(execution_id, version=4)
                execution = Execution.query.filter_by(id=execution_id).first()
            except Exception as error:
                raise error
        else:
            try:
                val = UUID(execution_id, version=4)
                execution = db.session.query(Execution) \
                    .filter(Execution.id == execution_id) \
                    .filter(Execution.user_id == user.id) \
                    .first()
            except Exception as error:
                raise error
        if not execution:
            raise ExecutionNotFound(message='Ticket Not Found')
        return execution

    @staticmethod
    def update_execution(execution, execution_id):
        logging.info('[SERVICE]: Updating execution')
        status = execution.get('status', None)
        progress = execution.get('progress', None)
        results = execution.get('results', None)
        if status is None and progress is None and results is None:
            raise Exception
        execution = ExecutionService.get_execution(execution_id=execution_id)
        if not execution:
            raise ExecutionNotFound(message='Execution with id '+execution_id+' does not exist')
        if status is not None:
            execution.status = status
            if status == 'FINISHED':
                execution.end_date = datetime.datetime.utcnow()
                execution.progress = 100
        if progress is not None:
            execution.progress = progress
        if results is not None:
            execution.results = results
        try:
            logging.info('[DB]: ADD')
            db.session.add(execution)
            db.session.commit()
        except Exception as error:
            raise error
        return execution

    @staticmethod
    def create_execution_log(log, execution_id):
        logging.info('[SERVICE]: Creating execution log')
        text = log.get('text', None)
        level = log.get('level', None)
        if text is None or level is None:
            raise Exception
        execution = ExecutionService.get_execution(execution_id=execution_id)
        if not execution:
            raise ExecutionNotFound(message='Execution with id '+execution_id+' does not exist')
        execution_log = ExecutionLog(text=text, level=level, execution_id=execution.id)
        try:
            logging.info('[DB]: ADD')
            db.session.add(execution_log)
            db.session.commit()
        except Exception as error:
            raise error
        return execution_log

    @staticmethod
    def get_execution_logs(execution_id, start_date, last_id):
        logging.info('[SERVICE]: Getting execution logs of execution %s: ' % (execution_id))
        logging.info('[DB]: QUERY')
        try:
            execution = ExecutionService.get_execution(execution_id=execution_id)
        except Exception as error:
            raise error
        if not execution:
            raise ExecutionNotFound(message='Execution with id '+execution_id+' does not exist')

        if start_date:
            logging.debug(start_date)
            return ExecutionLog.query.filter(ExecutionLog.execution_id == execution.id, ExecutionLog.register_date > start_date).order_by(ExecutionLog.register_date).all()
        elif last_id:
            return ExecutionLog.query.filter(ExecutionLog.execution_id == execution.id, ExecutionLog.id > last_id).order_by(ExecutionLog.register_date).all()
        else:
            return execution.logs
