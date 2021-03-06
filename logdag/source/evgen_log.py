#!/usr/bin/env python
# coding: utf-8

import logging

from amulog import config
from logdag import log2event
from . import evgen_common
from . import filter_log

_logger = logging.getLogger(__package__)

FEATURE_MEASUREMENT = "log_feature"


class LogEventDefinition(log2event.EventDefinition):

    _l_attr_log = ["gid", ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for attr in self._l_attr_log:
            setattr(self, attr, kwargs[attr])

    def __str__(self):
        return "{0}, gid:{1}({2})".format(self.host, str(self.gid),
                                          self.group)

    def key(self):
        return str(self.gid)

    def tags(self):
        return {"host": self.host,
                "key": self.key()}

    def series(self):
        return FEATURE_MEASUREMENT, self.tags()


class LogEventLoader(evgen_common.EventLoader):
    fields = ["val", ]

    def __init__(self, conf, dry=False):
        self.conf = conf
        self.dry = dry
        src = conf["general"]["log_source"]
        if src == "amulog":
            from . import source_amulog
            args = [config.getterm(conf, "general", "evdb_whole_term"),
                    conf["database_amulog"]["source_conf"],
                    conf["database_amulog"]["event_gid"]]
            self.source = source_amulog.AmulogLoader(*args)
        else:
            raise NotImplementedError
        self._filter_rules = config.getlist(conf, "filter", "rules")
        for method in self._filter_rules:
            assert method in filter_log.FUNCTIONS

        dst = conf["general"]["evdb"]
        if dst == "influx":
            dbname = conf["database_influx"]["log_dbname"]
            from . import influx
            self.evdb = influx.init_influx(conf, dbname, df=False)
            # self.evdb_df = influx.init_influx(conf, dbname, df = True)
        else:
            raise NotImplementedError

        self._lf = filter_log.init_logfilter(conf, self.source)
        self._feature_unit_diff = config.getdur(conf,
                                                "general", "evdb_unit_diff")

    def _evdef(self, host, gid, group):
        d = {"source": log2event.SRCCLS_LOG,
             "host": host,
             "group": group,
             "gid": gid}
        return LogEventDefinition(**d)

    def _apply_filter(self, l_dt, dt_range, ev):
        tmp_l_dt = l_dt
        for method in self._filter_rules:
            args = (tmp_l_dt, dt_range, ev)
            tmp_l_dt = getattr(self._lf, method)(*args)
            if method == "sizetest" and tmp_l_dt is None:
                # sizetest failure means skipping later tests
                # and leave all events
                return l_dt
            elif tmp_l_dt is None or len(tmp_l_dt) == 0:
                msg = "event {0} removed with {1}".format(ev, method)
                _logger.info(msg)
                return None
        return tmp_l_dt

    def read_all(self, dump_org=False):
        return self.read(dt_range=None, dump_org=dump_org)

    def read(self, dt_range=None, dump_org=False):
        if dt_range is not None:
            self.source.dt_range = dt_range

        for ev in self.source.iter_event():
            host, gid = ev
            l_dt = self.source.load(ev)
            if len(l_dt) == 0:
                _logger.info("log gid={0} host={1} is empty".format(
                    gid, host))
                continue
            if dump_org:
                self.dump("log_org", host, gid, l_dt)
                _logger.info("added org {0} size {1}".format(
                    (host, gid), len(l_dt)))
                pass
            feature_dt = self._apply_filter(l_dt, dt_range, ev)
            if feature_dt is not None:
                self.dump(FEATURE_MEASUREMENT, host, gid, feature_dt)
                _logger.info("added feature {0} size {1}".format(
                    (host, gid), len(feature_dt)))

    def dump(self, measure, host, gid, l_dt):
        if self.dry:
            return
        d_tags = {"host": host, "key": gid}
        data = {k: [v, ] for k, v in self.source.timestamp2dict(l_dt).items()}
        self.evdb.add(measure, d_tags, data, self.fields)
        self.evdb.commit()

    def all_feature(self):
        return [FEATURE_MEASUREMENT, ]

    def load_org(self, ev, dt_range):
        """Return: tuple(dt, host, msg)"""
        return self.source.load_org(ev, dt_range)

    def iter_evdef(self, dt_range=None, area=None):
        for host, gid in self.source.iter_event(dt_range=dt_range, area=area):
            group = self.source.label(gid)
            d = {"source": log2event.SRCCLS_LOG,
                 "host": host,
                 "group": group,
                 "gid": gid}
            yield LogEventDefinition(**d)

    def instruction(self, evdef):
        return "{0}: {1}".format(evdef.host, self.source.gid_instruction(evdef.gid))
