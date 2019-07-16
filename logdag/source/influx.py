#!/usr/bin/env python
# coding: utf-8

import numpy as np
import influxdb


class InfluxDB(object):

    def __init__(self, dbname, inf_kwargs,
                 batch_size = 1000, protocol = "line"):
        self.dbname = dbname
        self._precision = 's'
        self._batch_size = batch_size
        #self._protocol = protocol
        inf_kwargs["database"] = dbname
        self.client = influxdb.InfluxDBClient(**inf_kwargs)
        if not dbname in list(self._list_database()):
            raise IOError("No database {0}".format(dbname))
            #self.client.create_database(dbname)

    def _list_database(self):
        return [d["name"] for d in self.client.get_list_database()]

    def list_measurements(self):
        return [d["name"] for d in self.client.get_list_measurements()]

    def list_series(self, measure = None):
        ret = []
        if measure:
            rs = self.client.query("SHOW SERIES FROM \"{0}\"".format(measure))
        else:
            rs = self.client.query("SHOW SERIES")
        for p in rs.get_points():
            d = {}
            for s in p["key"].split(","):
                if "=" in s:
                    name, _, tag = s.partition("=")
                    d[name] = tag
            ret.append(d)
        return ret

    def add(self, measure, d_tags, d_input, columns):
        data = []
        for t, row in d_input.items():
            fields = {key: val for key, val in zip(columns, row)
                      if not (val is None or np.isnan(val))}
            if len(fields) == 0:
                continue
            d = {'measurement': measure,
                 'time': t,
                 'tags': d_tags,
                 'fields': fields}
            data.append(d)
        if len(data) > 0:
            self.client.write_points(data, database = self.dbname,
                                     time_precision = self._precision,
                                     batch_size = self._batch_size,
                                     #protocol = self._protocol,
                                     )
        return len(data)

    def commit(self):
        pass

    def get(self, measure, d_tags, fields, ut_range,
            str_bin = None, func = None, fill = None):
        if func is None:
            s_fields = ", ".join(["\"{0}\"".format(s) for s in fields])
        else:
            s_fields = ", ".join(["{0}(\"{1}\")".format(func, s)
                                  for s in fields])
        s_from = "\"{0}\".\"{1}\".\"{2}\"".format(self.dbname, self._rpolicy,
                                                  measure)
        s_where = " AND ".join(["{0} = {1}".format(k, v)
                                for k, v in d_tags.items()])
        s_where += " AND time >= {0} AND time < {1}".format(ut_range[0],
                                                            ut_range[1])
        if str_bin is None:
            s_gb = ""
        else:
            s_gb = " GROUP BY time({0})".format(str_bin)
            if fill is not None:
                s_gb += " fill({0})".format(str(fill))

        iql = "SELECT {0} FROM {1} WHERE {2}".format(
            s_fields, s_from, s_where)
        iql += s_gb

        _logger.debug("influxql query: {0}".format(iql))
        ret = self.client.query(iql)


class InfluxDF(InfluxDB):

    def __init__(self, dbname, inf_kwargs,
                 batch_size = 1000, protocol = "line"):
        self.dbname = dbname
        self._rpolicy = "autogen"
        self._precision = 's'
        self._batch_size = batch_size
        self._protocol = protocol
        inf_kwargs["database"] = dbname
        self.client = influxdb.DataFrameClient(**inf_kwargs)
        if not dbname in list(self._list_database()):
            raise IOError("No database {0}".format(dbname))
            #self.client.create_database(dbname)

    def add(self, measure, d_tags, df):
        self.client.write_points(df, database = self.dbname,
                                 measurement = measure, tags = d_tags,
                                 time_precision = self._precision,
                                 batch_size = self._batch_size,
                                 protocol = self._protocol)


def init_influx(conf, dbname, df = False):
    d = {}
    keys = ["host", "port", "username", "password"]
    for key in keys:
        v = conf["database_influx"][key].strip()
        if not (v is None or v == ""):
            d[key] = v
    batch_size = conf.getint("database_influx", "batch_size")
    protocol = conf["database_influx"]["protocol"]
    if df:
    	return InfluxDF(dbname, d, batch_size = batch_size,
                        protocol = protocol)
    else:
    	return InfluxDB(dbname, d, batch_size = batch_size,
                        protocol = protocol)


