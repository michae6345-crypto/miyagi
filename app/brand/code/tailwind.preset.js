// Tailwind preset: in tailwind.config.js, add `presets: [require('./tailwind.preset.js')]`.
module.exports = {
  theme: {
    extend: {
      colors: {
        paper: '#F6F6F3',
        surface: { DEFAULT: '#FFFFFF', 2: '#EFEFEA' },
        ink: { DEFAULT: '#141414', muted: '#66665F', faint: '#8F8F88' },
        pass: { DEFAULT: '#30D158', deep: '#1F9B45', text: '#1C8A3C' },
        offtrack: '#FFB020',
        watching: '#8E8E93',
        pill: '#000000',
      },
      fontFamily: {
        brand: ['"Google Sans Flex"', 'system-ui', 'sans-serif'],
        ui: ['-apple-system', 'BlinkMacSystemFont', '"SF Pro Text"', '"Segoe UI Variable Text"', '"Segoe UI"', 'system-ui', 'sans-serif'],
      },
      fontSize: { xs: '13px', sm: '15px', md: '20px', lg: '28px' },
      borderRadius: { chip: '14px', card: '20px', launcher: '28px', pill: '17px' },
      boxShadow: { card: '0 20px 60px rgba(0,0,0,.45)' },
    },
  },
};
