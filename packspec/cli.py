# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import print_function
from __future__ import absolute_import
# from __future__ import unicode_literals

import click
from . import helpers


# Module API

@click.command()
@click.argument('path', default='.')
def cli(path):
    specs = helpers.parse_specs(path)
    success = helpers.test_specs(specs)
    if not success:
        exit(1)


# Main program

if __name__ == '__main__':
    cli()
