/**
 * Feature: settings. The sample the Editor panel previews code settings on. Generic on purpose: it is not from any
 * lesson, only enough lines (one of them long) to show size, line numbers and wrapping.
 */
export const CODE_SAMPLE_CAPTION = 'Sample'
export const CODE_SAMPLE = [
  'def average(numbers):',
  '    total = 0',
  '    for n in numbers:',
  '        total += n',
  '    return total / len(numbers)',
  '',
  'print(average([3, 5, 8, 13]))  # a long comment on this line shows what happens when it runs past the edge of the card'
].join('\n')
