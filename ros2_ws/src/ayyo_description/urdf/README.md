# Robot-description source layout

This directory owns the authoritative Ayyo robot-description source. The root
`ayyo.urdf.xacro` file composes body, geometry, material, simulation, and future
control fragments. Frame and joint semantics belong here and must not be
duplicated in a simulator-specific model.

The current milestone uses clearly identified development geometry so the
frame tree can be validated before the final Ayyo mechanical design is
available. Final dimensions, mass properties, joint ranges, and mesh bindings
remain design inputs and must pass review before physical use.
