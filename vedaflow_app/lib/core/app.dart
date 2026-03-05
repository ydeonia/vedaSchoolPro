import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'router.dart';
import 'theme.dart';
import '../providers/branding_provider.dart';

/// Root app widget. Watches branding state to apply dynamic theme.
class VedaFlowApp extends ConsumerWidget {
  const VedaFlowApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final branding = ref.watch(brandingProvider);
    final appTheme = branding.when(
      data: (b) => AppTheme.fromHex(b.themeColor),
      loading: () => AppTheme.defaultTheme,
      error: (_, __) => AppTheme.defaultTheme,
    );

    return MaterialApp.router(
      title: 'VedaSchoolPro',
      debugShowCheckedModeBanner: false,
      theme: appTheme.toThemeData(),
      routerConfig: appRouter,
    );
  }
}
