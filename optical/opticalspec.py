#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © 2018 Michael J. Hayford
""" Container class for optical usage information

Created on Thu Jan 25 11:01:04 2018

@author: Michael J. Hayford
"""

import math
import numpy as np
from numpy.linalg import norm
from optical.firstorder import compute_first_order
from . import raytrace as rt
import util.colour_system as cs
srgb = cs.cs_srgb


class OpticalSpecs:
    """ Container class for optical usage information

    Contains optical usage information to specify the aperture, field of view
    and spectrum. It also supports model ray tracing in terms of relative
    aperture and field.

    It maintains a repository of paraxial data.
    """
    def __init__(self):
        self.spectral_region = WvlSpec()
        self.pupil = PupilSpec()
        self.field_of_view = FieldSpec()
        self.parax_data = None

    def __json_encode__(self):
        attrs = dict(vars(self))
        del attrs['parax_data']
        return attrs

    def set_from_list(self, dl):
        self.spectral_region = dl[0]
        self.pupil = dl[1]
        self.field_of_view = dl[2]

    def update_model(self, seq_model):
        stop = seq_model.stop_surface
        wl = self.spectral_region.central_wvl()
        self.parax_data = compute_first_order(seq_model, stop, wl)

    def trace(self, sm, pupil, fld, wl=None, eps=1.0e-12):
        if wl is None:
            wvl = self.spectral_region.central_wvl()
        else:
            wvl = self.spectral_region.wavelengths[wl]

        f = self.field_of_view.fields[fld]
        f.apply_vignetting(pupil)
        fod = self.parax_data[2]
        eprad = fod.enp_radius
        pt1 = np.array([eprad*pupil[0], eprad*pupil[1],
                        fod.obj_dist+fod.enp_dist])
        pt0 = self.obj_coords(f)
        dir0 = pt1 - pt0
        length = norm(dir0)
        dir0 = dir0/length
        return rt.trace(sm.path(), pt0, dir0, wvl, eps)

    def trace_fan(self, sm, fan_rng, fld, img_only=True, wl=None, eps=1.0e-12):
        if wl is None:
            wvl = self.spectral_region.central_wvl()
        else:
            wvl = self.spectral_region.wavelengths[wl]

        f = self.field_of_view.fields[fld]
        pt0 = self.obj_coords(f)
        fod = self.parax_data[2]
        eprad = fod.enp_radius
        start = np.array(fan_rng[0])
        stop = fan_rng[1]
        num = fan_rng[2]
        step = (stop - start)/(num - 1)
        fan = []
        for r in range(num):
            pupil = np.array(start)
            f.apply_vignetting(pupil)
            pt1 = np.array([eprad*pupil[0], eprad*pupil[1],
                            fod.obj_dist+fod.enp_dist])
            dir0 = pt1 - pt0
            length = norm(dir0)
            dir0 = dir0/length
            ray, op = rt.trace(sm.path(), pt0, dir0, wvl, eps)
            if img_only:
                fan.append([pupil, ray[-1][0]])
            else:
                fan.append([pupil, ray])

            start += step
        return fan

    def obj_coords(self, fld):
        fov = self.field_of_view
        fod = self.parax_data[2]
        if fov.type == 'OBJ_ANG':
            ang_dg = np.array([fld.x, fld.y, 0.0])
            dir_tan = np.tan(np.deg2rad(ang_dg))
            obj_pt = -dir_tan*(fod.obj_dist+fod.enp_dist)
        elif fov.type == 'IMG_HT':
            img_pt = np.array([fld.x, fld.y, 0.0])
            obj_pt = -fod.red*img_pt
        else:
            obj_pt = np.array([fld.x, fld.y, 0.0])
        return obj_pt


class WvlSpec:
    """ Class defining a spectral region

    A spectral region is a list of wavelengths (in nm) and corresponding
    weights. A reference wavelength index defines the "center" of the
    spectral region.

    """
    def __init__(self, wlwts=[(550., 1.)], ref_wl=0):
        self.set_from_list(wlwts)
        self.reference_wvl = ref_wl
        self.coating_wvl = 550.0

    def central_wvl(self):
        return self.wavelengths[self.reference_wvl]

    def set_from_list(self, wlwts):
        self.wavelengths = []
        self.spectral_wts = []
        for wlwt in wlwts:
            self.wavelengths.append(wlwt[0])
            self.spectral_wts.append(wlwt[1])
        self.calc_colors()

    def add(self, wl, wt):
        self.wavelengths.append(wl)
        self.spectral_wts.append(wt)
        self.spectrum.sort(key=lambda w: w[0], reverse=True)

    def calc_colors(self):
        self.render_colors = []
        num_wvls = len(self.wavelengths)
        if num_wvls == 1:
            self.render_colors.append('black')
        elif num_wvls == 2:
            self.render_colors.append('blue')
            self.render_colors.append('red')
        elif num_wvls == 3:
            self.render_colors.append('blue')
            self.render_colors.append('green')
            self.render_colors.append('red')
        else:
            for w in self.wavelengths:
                print("calc_colors", w)
                rgb = srgb.wvl_to_rgb(w)
                print("rgb", rgb)
                self.render_colors.append(rgb)


class PupilSpec:
    types = ('EPD', 'NA', 'NAO', 'FNO')

    def __init__(self, type='EPD', value=1.0):
        self.type = type
        self.value = value

    def set_from_list(self, ppl_spec):
        self.type = ppl_spec[0]
        self.value = ppl_spec[1]


class FieldSpec:
    types = ('OBJ_ANG', 'OBJ_HT', 'IMG_HT')

    def __init__(self, type='OBJ_ANG', flds=[0.], wide_angle=False):
        self.type = type
        self.fields = [Field() for f in range(len(flds))]
        for i, f in enumerate(self.fields):
            f.y = flds[i]
        self.wide_angle = wide_angle

    def set_from_list(self, flds):
        self.fields = [Field() for f in range(len(flds))]
        for i, f in enumerate(self.fields):
            f.y = flds[i]

    def update_fields_cv_input(self, tla, dlist):
        if tla == 'XOB' or tla == 'YOB':
            self.type = 'OBJ_HT'
        elif tla == 'XAN' or tla == 'YAN':
            self.type = 'OBJ_ANG'
        elif tla == 'XIM' or tla == 'YIM':
            self.type = 'IMG_HT'

        if len(self.fields) != len(dlist):
            self.fields = [Field() for f in range(len(dlist))]

        if tla[0] == 'V':
            attr = tla.lower()
        elif tla[0] == 'X' or tla[0] == 'Y':
            attr = tla[0].lower()
        elif tla == 'WTF':
            attr = 'wt'

        for i, f in enumerate(self.fields):
            f.__setattr__(attr, dlist[i])

    def max_field(self):
        max_fld = None
        max_fld_sqrd = 0.0
        for i, f in enumerate(self.fields):
            fld_sqrd = f.x*f.x + f.y*f.y
            if fld_sqrd > max_fld_sqrd:
                max_fld_sqrd = fld_sqrd
                max_fld = i
        return math.sqrt(max_fld_sqrd), max_fld


class Field:
    def __init__(self, x=0., y=0., wt=1.):
        self.x = x
        self.y = y
        self.vux = 0.0
        self.vuy = 0.0
        self.vlx = 0.0
        self.vly = 0.0
        self.wt = wt

    def apply_vignetting(self, pupil):
        if pupil[0] < 0.0:
            if self.vlx != 0.0:
                pupil[0] *= (1.0 - self.vlx)
        else:
            if self.vux != 0.0:
                pupil[0] *= (1.0 - self.vux)
        if pupil[1] < 0.0:
            if self.vly != 0.0:
                pupil[1] *= (1.0 - self.vly)
        else:
            if self.vuy != 0.0:
                pupil[1] *= (1.0 - self.vuy)
        return pupil
