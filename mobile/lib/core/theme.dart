import 'package:flutter/material.dart';

class FrequenIAColors {
  static const navy = Color(0xFF0B2740);
  static const blue = Color(0xFF145B84);
  static const cyan = Color(0xFF18B7B0);
  static const mint = Color(0xFFDDF7F3);
  static const background = Color(0xFFF4F8FA);
}

class FrequenIATheme {
  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme = ColorScheme.fromSeed(
      seedColor: FrequenIAColors.blue,
      brightness: brightness,
      primary: dark ? const Color(0xFF80CFFF) : FrequenIAColors.blue,
      secondary: FrequenIAColors.cyan,
      surface: dark ? const Color(0xFF122431) : Colors.white,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: dark
          ? const Color(0xFF091721)
          : FrequenIAColors.background,
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        foregroundColor: dark ? Colors.white : FrequenIAColors.navy,
        centerTitle: false,
        elevation: 0,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: scheme.surface,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(22),
          side: BorderSide(
            color: dark ? Colors.white10 : const Color(0xFFDDE7EC),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: dark ? Colors.white.withValues(alpha: .06) : Colors.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(
            color: dark ? Colors.white12 : const Color(0xFFD7E3E9),
          ),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 18,
          vertical: 17,
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: FrequenIAColors.navy,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(54),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(17),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 74,
        indicatorColor: dark ? FrequenIAColors.blue : FrequenIAColors.mint,
        labelTextStyle: WidgetStateProperty.all(
          const TextStyle(fontWeight: FontWeight.w700, fontSize: 12),
        ),
      ),
    );
  }
}
