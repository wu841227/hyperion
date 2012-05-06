from __future__ import print_function, division

import hashlib

import atpy
import numpy as np

from ..util.integrate import integrate_loglog
from ..util.interpolate import interp1d_fast_loglog
from ..util.functions import B_nu, FreezableClass, nu_common, \
                                    planck_nu_range, bool2str
from ..util.constants import sigma
from ..util.logger import logger


class Emissivities(FreezableClass):

    def __init__(self):

        self.is_lte = None
        self.var_name = None
        self.var = None
        self.nu = None
        self.jnu = None

        self._freeze()

    def normalize(self):
        for ivar in range(len(self.var)):
            norm = integrate_loglog(self.nu, self.jnu[:, ivar] / self.nu)
            self.jnu[:, ivar] /= norm

    def set_custom(self, filename):

        # Specify that emissivities are not LTE
        self.is_lte = False

        # Read in existing emissivities
        te = atpy.Table(filename, table='emissivities')

        # Set frequency scale and emissivities
        self.nu = te.nu
        self.jnu = te.jnu

        # Read in emissivity variable
        tev = atpy.Table(filename, table='emissivity_variable')

        # Only specific energy is considered a valid emissivity variable
        if tev.names[0] != 'specific_energy':
            raise Exception("Unknown emissivity variable: %s" % tev.names[0])

        # Set emissivity variable
        self.var_name = tev.names[0]

        # Find specific energy emissivity variable
        self.var = tev.specific_energy

    def set_lte(self, optical_properties, n_temp=1200, temp_min=0.1, temp_max=100000.):

        # Set temperatures to compute LTE emissivities for
        temperatures = np.logspace(np.log10(temp_min),
                                   np.log10(temp_max), n_temp)

        # Specify that emissivities are LTE
        self.is_lte = True

        # Set frequency scale
        planck_nu = planck_nu_range(temp_min, temp_max)
        self.nu = nu_common(planck_nu, optical_properties.nu)

        if planck_nu.min() < optical_properties.nu.min():
            logger.warn("Planck function for lowest temperature not completely covered by opacity function")
            self.nu = self.nu[self.nu >= optical_properties.nu.min()]

        if planck_nu.max() > optical_properties.nu.max():
            logger.warn("Planck function for highest temperature not completely covered by opacity function")
            self.nu = self.nu[self.nu <= optical_properties.nu.max()]

        # Compute opacity to absorption
        kappa_nu = interp1d_fast_loglog(optical_properties.nu,
                                        optical_properties.kappa, self.nu)

        # Compute LTE emissivities
        self.var_name = 'specific_energy'
        self.var = np.zeros(temperatures.shape)
        self.jnu = np.zeros((len(self.nu), n_temp))

        for it, T in enumerate(temperatures):

            # Find LTE emissivity
            self.jnu[:, it] = kappa_nu * B_nu(self.nu, T)

            # Find Planck mean opacity
            kappa_planck = optical_properties.kappa_planck_spectrum(self.nu, B_nu(self.nu, T))

            # Compute specific energy absorbed
            self.var[it] = 4. * sigma * T ** 4. * kappa_planck

    def to_table_set(self, table_set):

        if not self.all_set():
            raise Exception("Not all attributes of the emissivities are set")

        # Create emissivities table
        temiss = atpy.Table(name='emissivities')
        temiss.add_column('nu', self.nu)
        temiss.add_column('jnu', self.jnu)
        table_set.add_keyword('lte', bool2str(self.is_lte))

        # Write out the emissivity variable type
        if self.var_name == 'specific_energy':
            table_set.add_keyword('emissvar', 'E')
        else:
            raise Exception("Unknown emissivity variable: %s" % self.var_name)

        # Create emissivity variable table
        temissvar = atpy.Table(name='emissivity_variable')
        temissvar.add_column(self.var_name, self.var)

        # Add to table set
        table_set.append(temiss)
        table_set.append(temissvar)

    def from_table_set(self, table_set):

        # Read emissivities
        temiss = table_set['emissivities']
        self.nu = temiss['nu']
        self.jnu = temiss['jnu']
        self.is_lte = table_set.keywords['lte'] == 'yes'

        # Find the emissivity variable type
        if table_set.keywords['emissvar'] == 'E':
            self.var_name = 'specific_energy'
        else:
            raise Exception("Unknown emissivity variable: %s" %
                            table_set.keywords['emissvar'])

        # Read in emissivity variable
        temissvar = table_set['emissivity_variable']
        self.var = temissvar[self.var_name]

    def all_set(self):
        return self.is_lte is not None and \
               self.var_name is not None and \
               self.var is not None and \
               self.nu is not None and \
               self.jnu is not None

    def plot(self, figure, subplot):

        if not self.all_set():
            raise Exception("Not all attributes of the emissivities are set")

        import matplotlib.pyplot as plt

        self.normalize()
        peak = self.jnu.max()

        m = plt.cm.gist_heat
        vmin, vmax = np.log10(peak) - 6., np.log10(peak)

        ax = figure.add_subplot(subplot)
        ax.patch.set_facecolor('black')
        ax.contourf(self.nu, self.var,
                     np.log10(np.clip(np.abs(self.jnu.swapaxes(0, 1)), 10.**vmin, 10.**vmax)),
                     np.linspace(vmin, vmax, 30),
                     cmap=m)
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlim(self.nu.min(), self.nu.max())
        ax.set_ylim(self.var.min(), self.var.max())
        ax.set_title('Emissivities', y=0.9, verticalalignment='top',
                     color='white')

        ax.set_xlabel("Specific energy (ergs/s/g)")
        ax.set_ylabel("Wavelength (microns)")

        return figure

    def hash(self):
        h = hashlib.md5()
        h.update(str(self.is_lte).encode('utf-8'))
        h.update(self.var_name.encode('utf-8'))
        h.update(self.var)
        h.update(self.nu)
        h.update(self.jnu)
        return h.hexdigest()
