"""AxizPOS UAE e-Invoicing plugin.

Separate process and package. It reads the existing AxizPOS PostgreSQL database and
owns only the einvoicing_* tables. It does not recalculate VAT on a posted sale.
"""

__version__ = "0.1.0"
