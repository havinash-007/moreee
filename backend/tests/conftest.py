import os

os.environ.setdefault("CATALOGUE_AUTO_REFRESH", "false")  # tests must never hit the network on startup
