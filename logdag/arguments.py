#!/usr/bin/env python
# coding: utf-8

import os
import logging

from . import dtutil
from amulog import config
from amulog import common

DEFAULT_CONFIG = "/".join((os.path.dirname(__file__),
                           "data/config.conf.default"))
_logger = logging.getLogger(__package__)
_amulog_logger = logging.getLogger("amulog")


class ArgumentManager(object):
    _args_filename = "args"

    def __init__(self, conf):
        self._conf = conf
        output_dir = self._output_dir(conf)
        common.mkdir(output_dir)
        self.args_path = "{0}/{1}".format(output_dir,
                                          self._args_filename)
        self.l_args = []
        # self.args_filename = conf.get("dag", "args_fn")
        # self.l_args = []
        # if self.args_filename.strip() == "":
        #    confname = conf.get("general", "base_filename").split("/")[-1]
        #    self.args_filename = "args_{0}".format(confname)

    def __iter__(self):
        return self.l_args.__iter__()

    def __getitem__(self, i):
        return self.l_args[i]

    def __len__(self):
        return len(self.l_args)

    def generate(self, func):
        self.l_args = func(self._conf)

    def add(self, args):
        self.l_args.append(args)

    def areas(self):
        return set([args[2] for args in self.l_args])

    def args_in_area(self, area):
        return [args for args in self.l_args if args[2] == area]

    def args_in_time(self, dt_range):
        return [args for args in self.l_args if args[1] == dt_range]

    def args_from_time(self, dt):
        for args in self.l_args:
            dts, dte = args[1]
            if dts <= dt < dte:
                yield args

    def show(self):
        table = [["name", "datetime", "area"]]
        for args in self.l_args:
            conf, dt_range, area = args
            temp = [self.jobname(args),
                    "{0} - {1}".format(dt_range[0], dt_range[1]), area]
            table.append(temp)
        return common.cli_table(table, spl=" | ")

    def dump(self):
        with open(self.args_path, 'w') as f:
            f.write("\n".join([self.jobname(args) for args in self.l_args]))

    def load(self):
        self.l_args = []
        with open(self.args_path, 'r') as f:
            for line in f:
                args = self.jobname2args(line.rstrip(), self._conf)
                self.l_args.append(args)

    @staticmethod
    def jobname(args):
        def dt_filename(tmp_dt_range):
            dts, dte = tmp_dt_range
            if dtutil.is_intdate(dts) and dtutil.is_intdate(dte):
                return dts.strftime("%Y%m%d")
            else:
                return dts.strftime("%Y%m%d_%H%M%S")

        conf, dt_range, area = args
        return "_".join([area, dt_filename(dt_range)])

    @staticmethod
    def jobname2args(name, conf):
        area, dtstr = name.split("_", 1)
        dts = dtutil.shortstr2dt(dtstr)
        term = config.getdur(conf, "dag", "unit_term")
        dte = dts + term
        return conf, (dts, dte), area

    @staticmethod
    def _output_dir(conf):
        return conf.get("dag", "output_dir")

    @staticmethod
    def _arg_dirname(output_dir, argname):
        return "{0}/{1}".format(output_dir, argname)

    @classmethod
    def dag_path(cls, conf, args, ext="pickle"):
        dirname = cls._arg_dirname(cls._output_dir(conf),
                                   cls.jobname(args))
        # try <- compatibility
        try:
            common.mkdir(dirname)
        except OSError:
            return
        return dirname + "/dag.{0}".format(ext)

    @classmethod
    def evdef_path(cls, args):
        conf, dt_range, area = args
        dirname = cls._arg_dirname(cls._output_dir(conf),
                                   cls.jobname(args))
        # try <- compatibility
        try:
            common.mkdir(dirname)
        except OSError:
            return
        return dirname + "/evdef.pickle"

    #@classmethod
    #def output_filename(cls, dirname, args):
    #    return "{0}/{1}".format(dirname, cls.jobname(args))

    #@staticmethod
    #def evdef_dir(conf):
    #    dirname = conf.get("dag", "evmap_dir")
    #    if dirname == "":
    #        dirname = conf.get("dag", "output_dir")
    #    else:
    #        common.mkdir(dirname)

    @classmethod
    def evdef_path_old(cls, args):
        conf, dt_range, area = args
        dirname = conf.get("dag", "evmap_dir")
        filename = cls.jobname(args)
        if dirname == "":
            dirname = conf.get("dag", "output_dir")
            filename = filename + "_def"
        else:
            common.mkdir(dirname)
        return "{0}/{1}".format(dirname, filename)

    #@staticmethod
    #def dag_dir(conf):
    #    dirname = conf.get("dag", "output_dir")
    #    common.mkdir(dirname)

    @classmethod
    def dag_path_old(cls, args):
        conf, dt_range, area = args
        dirname = conf.get("dag", "output_dir")
        common.mkdir(dirname)
        filename = cls.jobname(args)
        return "{0}/{1}".format(dirname, filename)

    def init_dirs(self, conf):
        # TODO for compatibility
        pass
        #self.evdef_dir(conf)
        #self.dag_dir(conf)

    def iter_dt_range(self):
        s = set()
        for args in self.l_args:
            s.add(args[1])
        return list(s)


def args2name(args):
    return ArgumentManager.jobname(args)


def name2args(name, conf):
    return ArgumentManager.jobname2args(name, conf)


def open_logdag_config(conf_path, debug=False):
    conf = config.open_config(conf_path, ex_defaults=[DEFAULT_CONFIG])
    lv = logging.DEBUG if debug else logging.INFO
    am_logger = logging.getLogger("amulog")
    config.set_common_logging(conf, logger=[_logger, am_logger], lv=lv)
    return conf


def open_amulog_config(conf):
    conf_fn = conf["database_amulog"]["source_conf"]
    return config.open_config(conf_fn)


def all_args(conf):
    amulog_conf = config.open_config(conf["database_amulog"]["source_conf"])
    from amulog import log_db
    ld = log_db.LogData(amulog_conf)
    w_top_dt, w_end_dt = config.getterm(conf, "dag", "whole_term")
    term = config.getdur(conf, "dag", "unit_term")
    diff = config.getdur(conf, "dag", "unit_diff")

    l_args = []
    top_dt = w_top_dt
    while top_dt < w_end_dt:
        end_dt = top_dt + term
        l_area = config.getlist(conf, "dag", "area")
        if "each" in l_area:
            l_area.pop(l_area.index("each"))
            l_area += ["host_" + host for host
                       in ld.whole_host(top_dt, end_dt)]
        for area in l_area:
            l_args.append((conf, (top_dt, end_dt), area))
        top_dt = top_dt + diff
    return l_args


def all_terms(conf, term, diff, w_term=None):
    w_top_dt, w_end_dt = config.getterm(conf, "dag", "whole_term")

    l_args = []
    top_dt = w_top_dt
    while top_dt < w_end_dt:
        end_dt = top_dt + term
        l_args.append((conf, (top_dt, end_dt)))
        top_dt = top_dt + diff
    return l_args
