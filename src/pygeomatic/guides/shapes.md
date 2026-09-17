# Shapes, measurements and styling

The drawable shapes, how they stay attached to the points they are built from, what can be measured, and how to color, label and annotate them.

## Shapes follow their points

A shape keeps live links to the nodes it was built from. Build shapes from named points
and scalars, and everything moves when those change:

```python
a = gm.point(-2, -1)
b = gm.point(3, -1)
c = gm.point(0, 3)
tri = gm.triangle(a, b, c)
side = gm.line(a, b)
mid = gm.mid_point(a, b)
median = gm.line(c, mid)
r = gm.scalar(1)
dot = gm.circle(mid, r)
```

Changing `a` moves `tri`, `side`, `mid`, `median` and `dot`. A shape made from typed
numbers instead (`gm.line(gm.point(-2, -1), gm.point(3, -1))`) is also fine, but nothing
else can drive it.

## The canvas

The origin (0, 0) is the center. At the default zoom (`gm.unit` = 50 pixels per unit)
the visible area is about -6 to 6 on each axis. `gm.p0` is the origin and is the default
center of `circle`, `ellipse`, `arc`, `regular_polygon`, and the default corner of
`square` and `rectangle`.

## Shapes

| Call | Makes |
| --- | --- |
| `point(x, y)` | a point |
| `line(p1, p2)` | a line segment |
| `triangle(v1, v2, v3)` | a triangle |
| `polygon(v1, v2, v3, ...)` | a polygon through the given points |
| `polyline(p1, p2, ...)` | an Array of Lines joining the points in order |
| `convex_hull(p1, p2, ...)` | the convex hull polygon |
| `regular_polygon(center, radius, numVertices, startAngle)` | a regular polygon |
| `polygon_from_side(a, b, n)` | a regular n-gon with side `a`-`b` |
| `square(bottomLeft, side, angle)`, `rectangle(bottomLeft, width, height, angle)` | polygons |
| `circle(center, radius)` | a circle |
| `ellipse(center, radiusX, radiusY, rotation)`, `ellipse_from_foci(f1, f2, stringLength)` | an ellipse |
| `arc(center, radius, startAngle, endAngle)` | an arc; angles in degrees |
| `bezier_quadratic(p1, control, p2)`, `bezier_cubic(p1, c1, c2, p2)` | Bézier curves |
| `polynomial(a0, a1, ...)` | the curve y = a0 + a1·x + ...; `evaluate_polynomial(poly, x)` reads it |
| `tangent(curve, x, length)` | the tangent Line to a Plot or Polynomial at `x` |

## Reading parts of shapes

Only these properties can be read (each is a live node):

- Point: `.x`, `.y`
- Line, Arrow: `.p1`, `.p2`
- Circle: `.center`, `.radius`
- Ellipse: `.center`, `.radiusX`, `.radiusY`, `.rotation`
- Arc: `.center`, `.radius`, `.startAngle`, `.endAngle`
- RegularPolygon: `.center`, `.radius`, `.numVertices`, `.startAngle`
- BezierQuadratic: `.p1`, `.control`, `.p2`; BezierCubic: `.p1`, `.control1`,
  `.control2`, `.p2`
- Triangle, Polygon: `.vertices` (an Array of Points)
- Array: `.length`

Chains are fine: `circ.center.x`. `gm.x_coord(p)` and `gm.y_coord(p)` are the same as
`p.x` and `p.y`.

## Points derived from shapes

- `mid_point(p1, p2)`, `centroid(tri)`, `circumcenter(tri)`, `incenter(tri)`
- `project_point(point, line)`, `reflect_point(point, line)`
- `intersection_line_line(l1, l2)` returns a Point.
- `intersection_line_circle`, `intersection_line_ellipse`, `intersection_circle_circle`,
  `intersection_line_bezier_quadratic` return an Array of Points. Take one with `hits[0]`.
- `bisect_angle(l1, l2)` returns a Line.

## Measurements

All return live Scalars:

- `distance(p1, p2)` (`p2` defaults to the origin)
- `angle(p1, vertex, p3)`: the angle at `vertex`, in degrees
- `slope_of_line(line)`: the line's direction angle in radians, from 0 up to 2π
- `area_triangle(tri)`, `area_circle(circ)`

## Color and visibility

Load the palette once, then use its names:

```python
col = gm.load_colors()
ring = gm.circle(gm.p0, 2)
gm.set_stroke(ring, col.BLUE)
tile = gm.square(gm.p0, 1)
gm.set_fill(tile, col.AMBER)
gm.set_stroke(tile, col["COLOR-TEAL-LIGHT"])     # names with a dash need []
```

Names: RED, ORANGE, AMBER, YELLOW, LIME, GREEN, EMERALD, TEAL, VOLT, CYAN, BLUE, INDIGO,
VIOLET, PURPLE, PINK, FUCHSIA, WHITE, GRAY, DARKGRAY, BLACK, and the shades GRAY-LIGHT,
GRAY-MID, GRAY-DARK, TEAL-LIGHT, TEAL-MID, TEAL-DARK, RED-LIGHT, RED-MID, RED-DARK. The
canvas is dark, so keep WHITE and the grays for background lines.

- `highlight(*nodes)` briefly flashes nodes to draw attention.
- `hide(*nodes)` and `show(*nodes)` toggle visibility; a hidden node still computes.
- `remove(*nodes)` deletes nodes; removing an array also removes its elements, even
  named points it was made from.
- `hide`, `show`, `set_stroke` and `set_fill` on an array reach all its elements (see
  the `arrays` guide).
- `gm.grid_opacity` set to 0 hides the grid; `gm.grid_bg_color` sets a background color.

## Text

`gm.text` is plain, single-line text. Use Unicode (`θ`, `λ₁`, `v²`), never LaTeX.
`${name}` inside the text shows a node's live value; an f-string does the same.

```python
r = gm.scalar(2)
label = gm.annotate_text_box("r = ${r}", 3, 3)
```

## Annotations

- `annotate_text_box(text, x, y, fontSize=14, width=0, height=0)`: `(x, y)` is the center
  of the box; `fontSize` is in pixels; `width` and `height` are canvas units (0 = fit the
  text).
- `annotate_arrow(p1, p2, padding=0, label='')` and
  `annotate_curved_arrow(p1, p2, control, padding=0, label='')`: `padding` is a fraction
  of the length from 0 to 0.5, not a distance.
- `annotate_dim_line(p1, p2, label='')`, `annotate_curly_bracket(p1, p2, label='')`,
  `annotate_leader_line(p1, p2, label)`, `annotate_pin(position, label='')`
- `annotate_angle_mark(line1, line2, label='')`: both lines must start from the same
  point node, or nothing is drawn.

Arrowheads, offsets and label boxes keep the same size on screen at any zoom.

```python
o = gm.point(0, 0)
x_end = gm.point(3, 0)
y_end = gm.point(0, 2)
x_axis = gm.line(o, x_end)
y_axis = gm.line(o, y_end)
gm.annotate_angle_mark(x_axis, y_axis, "90°")
gm.annotate_arrow(o, gm.point(2, 2), 0.1, "v")
```
