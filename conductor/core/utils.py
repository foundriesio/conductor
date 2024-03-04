# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import datetime
import json


class ISO8601_JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat() + '+00:00'
        return super().default(obj)
