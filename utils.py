import micropython, math

@micropython.asm_thumb
def asm_lerp_unit(r0, r1, r2): 
    mov(r3, 255)
    add(r3, r3, 1)
    sub(r3, r3, r2)
    mul(r0, r3)
    mul(r1, r2)
    add(r0, r0, r1)
    lsr(r0, r0, 8)

@micropython.viper
def get_bezier_point(t_int: int, p0: int, p1: int, p2: int) -> int:
    inv_t = 256 - t_int
    # Optimized to avoid intermediate large integers
    return (inv_t * inv_t * p0 + 2 * inv_t * t_int * p1 + t_int * t_int * p2) >> 16

@micropython.viper
def fast_dimmer(display_obj, pen: int):
    # Pass a pre-cached pen to avoid per-frame heap allocation
    d = display_obj
    d.set_pen(pen)
    for y in range(0, 240, 3):
        d.line(0, y, 320, y)

def get_asm_pen(display, c1, c2, t):
    tf = int(t * 256)
    return display.create_pen(
        asm_lerp_unit(c1[0], c2[0], tf),
        asm_lerp_unit(c1[1], c2[1], tf),
        asm_lerp_unit(c1[2], c2[2], tf)
    )