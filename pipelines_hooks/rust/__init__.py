"""Rust lexical scanning shared by the complexity terms and the KISS diff scope.

Comment, literal and balanced-delimiter recognition is one authority, so the
gates that read Rust source can never disagree about what they see. Source
that cannot be lexed raises :class:`pipelines_hooks.rust.mask.RustLexError`,
which every caller treats as "not provable", never as a pass.
"""
