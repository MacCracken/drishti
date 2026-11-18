// quant_libaom.c — libaom's OWN "B" quantizer, driven from stdin, for scripts/refs/quant_ref.py.
//
// The AV1 spec defines only dequantization (7.12.3); the quantizer is the encoder's choice. drishti's is libaom's
// dead-zone "B" quantizer rule set computed in exact integer arithmetic (quant_ref.py); this harness runs libaom's own:
// av1_build_quantizer (av1/encoder/av1_quantize.c: zbin, round, the invert_quant reciprocal) and
// aom_highbd_quantize_b_helper_c (aom_dsp/quantize.c, the 64-bit path every bit depth can take), compiled from the
// source in ref/ (gitignored; see ref/README.md), not transcribed.
//
// Build (quant_ref.py --libaom does this):
//   cc -O1 -I ref/aom -I ref/aom-build scripts/refs/quant_libaom.c ref/aom-build/libaom.a -lm -lpthread \
//      -o build/quant_libaom
//
// Protocol: one request per line, one line back.
//   q BD QINDEX YDC UDC UAC VDC VAC PLANE LOGSCALE N c[0..N-1]
// quantizes N coefficients (c[0] the DC, the rest AC) of plane 0/1/2 at qindex QINDEX with those frame deltas; prints
// the N levels then the N dequantized values libaom's encoder reconstructs from.

#include <stdio.h>
#include <string.h>

#include "config/aom_dsp_rtcd.h"
#include "config/av1_rtcd.h"
#include "aom_dsp/quantize.h"
#include "av1/encoder/av1_quantize.h"

static QUANTS quants;
static Dequants deq;

int main(void) {
  char cmd[8];
  int built = 0, have[6] = { 0 };
  static tran_low_t coeff[4096], qcoeff[4096], dqcoeff[4096];
  static int16_t scan[4096];
  for (int i = 0; i < 4096; i++) scan[i] = (int16_t)i;
  aom_dsp_rtcd();
  av1_rtcd();
  while (scanf("%7s", cmd) == 1) {
    if (strcmp(cmd, "q") != 0) return 4;
    int bd, qindex, d[5], plane, log_scale, n;
    if (scanf("%d %d %d %d %d %d %d %d %d %d", &bd, &qindex, &d[0], &d[1], &d[2], &d[3], &d[4], &plane, &log_scale,
              &n) != 10)
      return 2;
    if (!built || have[0] != bd || memcmp(have + 1, d, sizeof(d)) != 0) {
      av1_build_quantizer((aom_bit_depth_t)bd, d[0], d[1], d[2], d[3], d[4], &quants, &deq, 0);
      built = 1;
      have[0] = bd;
      memcpy(have + 1, d, sizeof(d));
    }
    for (int i = 0; i < n; i++) {
      int v;
      if (scanf("%d", &v) != 1) return 2;
      coeff[i] = v;
    }
    const int16_t *zbin = plane == 0 ? quants.y_zbin[qindex] : plane == 1 ? quants.u_zbin[qindex] : quants.v_zbin[qindex];
    const int16_t *round = plane == 0 ? quants.y_round[qindex]
                           : plane == 1 ? quants.u_round[qindex]
                                        : quants.v_round[qindex];
    const int16_t *quant = plane == 0 ? quants.y_quant[qindex]
                           : plane == 1 ? quants.u_quant[qindex]
                                        : quants.v_quant[qindex];
    const int16_t *shift = plane == 0 ? quants.y_quant_shift[qindex]
                           : plane == 1 ? quants.u_quant_shift[qindex]
                                        : quants.v_quant_shift[qindex];
    const int16_t *dq = plane == 0 ? deq.y_dequant_QTX[qindex]
                        : plane == 1 ? deq.u_dequant_QTX[qindex]
                                     : deq.v_dequant_QTX[qindex];
    uint16_t eob = 0;
    aom_highbd_quantize_b_helper_c(coeff, n, zbin, round, quant, shift, qcoeff, dqcoeff, dq, &eob, scan, scan, NULL,
                                   NULL, log_scale);
    for (int i = 0; i < n; i++) printf(i ? " %d" : "%d", (int)qcoeff[i]);
    for (int i = 0; i < n; i++) printf(" %d", (int)dqcoeff[i]);
    printf("\n");
    fflush(stdout);
  }
  return 0;
}
