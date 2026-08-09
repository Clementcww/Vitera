/* Can this machine render the 3D view at all?
 *
 * Probed once, before the three.js chunk is fetched, because the demo runs on
 * a projector and a borrowed laptop and criterion 8 says a system that fails
 * on stage scores near zero regardless of everything else. A capability check
 * plus a real 2D fallback turns "the 3D view crashed" into "the 3D view is
 * unavailable, here is the same data".
 *
 * Deliberately conservative: a context that allocates and then reports a
 * software renderer still counts as unavailable, because a 300-bar scene on
 * SwiftShader is a slideshow, and a slideshow on stage reads as a hang. */

export function webglAvailable(): { ok: boolean; reason?: string } {
  if (typeof WebGLRenderingContext === 'undefined') {
    return { ok: false, reason: 'WebGL tidak tersedia di peramban ini' }
  }
  try {
    const canvas = document.createElement('canvas')
    const gl =
      canvas.getContext('webgl2') ??
      (canvas.getContext('webgl') as WebGLRenderingContext | null)
    if (!gl) return { ok: false, reason: 'Konteks WebGL tidak dapat dibuat' }

    const dbg = gl.getExtension('WEBGL_debug_renderer_info')
    const renderer = dbg
      ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL))
      : ''
    if (/swiftshader|llvmpipe|software/i.test(renderer)) {
      return { ok: false, reason: `Perender perangkat lunak (${renderer})` }
    }
    return { ok: true }
  } catch (e) {
    return { ok: false, reason: String(e) }
  }
}
