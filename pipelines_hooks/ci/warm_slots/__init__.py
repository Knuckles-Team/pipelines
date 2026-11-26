"""Warm build slots: a pinned image and a local cache volume that keep pull request CI fast.

``definition`` checks the slot image and cache against the repository pins,
``config`` reads the one shared configuration file, ``render`` writes it for
each runtime, ``lifecycle`` runs ``status``, ``up``, ``down`` and ``upgrade``
through injected adapters, ``routing`` checks pull request routing and
credential isolation, and ``budgets`` checks the recorded timings.
"""
