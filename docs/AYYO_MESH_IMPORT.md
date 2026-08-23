# Final Ayyo Mesh Import Workflow

## Purpose and current gate

This is the required workflow for replacing development proxy geometry with
the reviewed Ayyo mechanical design. Foundation v1 contains no final visual or
collision mesh. Do not set `use_meshes:=true` for a passing validation until
every required asset exists and the complete gate below is recorded.

The workflow changes geometry and verified design data, not canonical link and
joint names. A required frame or joint semantic change is a separate
architecture review, never an incidental mesh-import edit.

## 1. Freeze the source design revision

Record the source CAD application, document/revision identifier, export date,
designer, intended robot revision, and asset rights. Freeze the kinematic
assembly and identify which CAD body owns each part named in
`ros2_ws/src/ayyo_description/meshes/mesh_contract.json`.

Do not export cosmetic assembly transforms as unreviewed URDF joint transforms.
Resolve discrepancies between CAD datums and the documented frame tree before
creating repository assets.

## 2. Verify mechanical datums and joint contracts

For every link, verify its parent joint datum, child joint datum, zero pose,
positive rotation axis, hard range, intended actuator, and mass-property source
against `ROBOT_DESCRIPTION_SIMULATION.md`.

Classify each current origin, dimension, inertia, effort, velocity, and limit as
confirmed, replaced, or still unknown. Unknown physical values cannot be
promoted from proxy values.

## 3. Export one visual mesh per manifest part

Export high-fidelity appearance assets as Collada `.dae` files named exactly:

```text
meshes/visual/<part>.dae
```

Use the 33 manifest names without case or suffix variation. Preserve only
rendering-relevant detail. Remove invisible CAD internals, construction
geometry, duplicates, non-manifold fragments, zero-area faces, and unrelated
assembly parts. Recalculate and inspect normals. Apply transforms before
export.

DAE materials and textures are authoritative in mesh mode. Keep textures
self-contained or at package-relative paths under `meshes/visual/`; never emit
an absolute workstation path, external URL, or network dependency.

## 4. Normalize coordinates and scale

Normalize vertices before repository import:

- right-handed REP-103 coordinates;
- `+x` forward, `+y` left, `+z` up;
- vertex units in metres;
- runtime scale exactly `1 1 1`; and
- no exporter-specific axis correction left for Xacro to guess.

Verify scale against at least two independent known CAD dimensions and record
the measured mesh bounds. STL files are unitless, so the export procedure must
explicitly preserve the metre convention.

## 5. Place each mesh origin at its link frame

Set each asset's origin/pivot to the documented owning link frame in the zero
pose. A mesh should load with visual and collision origins at `0 0 0` unless an
explicit, reviewed local offset is justified.

Do not compensate for a wrong pivot by changing a canonical parent/child joint
origin. Fix the asset or conduct a separate frame-contract review.

## 6. Generate independent collision geometry

Create simulation-appropriate collision assets as:

```text
meshes/collision/<part>.stl
```

Collision meshes must be watertight, low-complexity, correctly wound, and
appropriate for the intended contact behavior. Use reviewed primitives, convex
hulls, or convex decomposition where possible. Remove cosmetic detail, thin
features, cavities, self-intersections, and disconnected debris that do not
serve collision behavior.

Never copy a high-polygon visual mesh into the collision directory merely to
satisfy the filename contract. Record triangle counts, decomposition method,
and any deliberately excluded contact feature.

## 7. Update mass and inertia from authoritative data

Obtain mass, centre of mass, and inertia tensors from the controlled mechanical
model or validated measurements. Express each tensor at the URDF inertial
origin in the link frame and verify positive mass, finite values, symmetry, and
physical plausibility.

Proxy box inertias must not survive into a claimed dynamics validation unless
they independently match reviewed data.

## 8. Bind assets without changing kinematic semantics

Add all expected `.dae` and `.stl` files, then update
`mesh_contract.json` from `final_assets_not_present` only as part of the same
review that verifies completeness. Keep package URIs and runtime scale
unchanged:

```text
package://ayyo_description/meshes/visual/<part>.dae
package://ayyo_description/meshes/collision/<part>.stl
```

If body-region subdirectories are later justified, update the manifest and
geometry macro atomically while retaining manifest part identities. Do not add
a second URDF or simulator-specific Ayyo model.

## 9. Run deterministic structural validation

From the repository root:

```bash
source /opt/ros/jazzy/setup.bash
python3 ros2_ws/src/ayyo_description/scripts/validate_description.py
./scripts/build_workspace.sh
./scripts/test_workspace.sh
```

Inspect the mesh-mode expansion and reject absolute paths:

```bash
xacro ros2_ws/src/ayyo_description/urdf/ayyo.urdf.xacro \
  use_meshes:=true > /tmp/ayyo-final-mesh-review.urdf
check_urdf /tmp/ayyo-final-mesh-review.urdf
rg '/home/|file://' /tmp/ayyo-final-mesh-review.urdf
```

The final `rg` command must return no match. Remove the temporary review file
afterward.

## 10. Perform and record RViz inspection

After building and sourcing `ros2_ws/install/setup.bash`:

```bash
ros2 launch ayyo_description view_robot.launch.py \
  use_meshes:=true use_joint_state_publisher_gui:=true
```

Inspect and record:

- forward/up orientation and metre scale;
- base, pelvis, torso, chest, neck, head, and sensor mount placement;
- left/right identity and symmetry;
- link continuity and gaps;
- mesh pivots at every joint;
- positive rotation direction and full intended range;
- visual material and texture resolution;
- clipping and self-intersections; and
- collision-to-visual alignment with collision rendering enabled.

Screenshots or a review record must identify the asset revision. Successful
rendering alone is not approval.

## 11. Perform and record Gazebo Harmonic inspection

```bash
ros2 launch ayyo_simulation simulation.launch.py \
  headless:=false use_meshes:=true spawn_z:=<reviewed_base_height>
```

Inspect scale, orientation, ground contact, model pose, mesh/material loading,
collision alignment, clipping, and server/client errors. Confirm the robot is
still static and non-actuating in this foundation launch.

Do not infer dynamics quality from a static spawn.

## 12. Gate dynamics and future control separately

Only after visual/collision review should a later milestone validate mass,
centre of mass, inertia, friction, contact behavior, joint damping, limits,
controller update rate, transmissions, and the selected `gz_ros2_control`
system.

That integration must invoke the dormant ros2_control macro with one reviewed
simulation plugin, add explicit controller configuration, start with a
joint-state broadcaster, and keep command controllers disabled until their
typed Runtime Bridge adapter and dedicated motion/contact safety boundary are
reviewed. Simulation success never authorizes physical hardware.

## Import acceptance record

The review is complete only when it records:

- source design revision and owner;
- manifest completeness for all 33 visual and 33 collision assets;
- coordinate, scale, pivot, and bounds evidence;
- visual and collision cleanup evidence;
- mass/inertia provenance;
- deterministic validator and complete regression results;
- RViz checklist results;
- Gazebo checklist results;
- remaining design-dependent values; and
- reviewer decision without claiming physical-safety certification.
