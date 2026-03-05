import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../core/config.dart';
import '../../core/storage.dart';
import '../../providers/auth_provider.dart';
import '../../providers/branding_provider.dart';
import '../../widgets/animated_card.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen>
    with TickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _loginIdCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _obscurePassword = true;
  bool _rememberMe = false;
  late AnimationController _logoAnimCtrl;
  late Animation<double> _logoScale;
  late AnimationController _formAnimCtrl;

  @override
  void initState() {
    super.initState();
    _rememberMe = LocalStorage.rememberMe;
    if (_rememberMe && LocalStorage.savedLoginId != null) {
      _loginIdCtrl.text = LocalStorage.savedLoginId!;
    }

    // Logo bounce-in animation
    _logoAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _logoScale = CurvedAnimation(
      parent: _logoAnimCtrl,
      curve: Curves.elasticOut,
    );
    _logoAnimCtrl.forward();

    // Form slide-up animation
    _formAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted) _formAnimCtrl.forward();
    });
  }

  @override
  void dispose() {
    _loginIdCtrl.dispose();
    _passwordCtrl.dispose();
    _logoAnimCtrl.dispose();
    _formAnimCtrl.dispose();
    super.dispose();
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) return;
    HapticFeedback.lightImpact();

    // Save remember-me preference
    LocalStorage.rememberMe = _rememberMe;
    if (_rememberMe) {
      LocalStorage.savedLoginId = _loginIdCtrl.text.trim();
    } else {
      LocalStorage.savedLoginId = null;
    }

    await ref.read(authProvider.notifier).login(
          _loginIdCtrl.text.trim(),
          _passwordCtrl.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final branding = ref.watch(brandingProvider);
    final theme = Theme.of(context);
    // Navigate on auth state changes
    ref.listen(authProvider, (prev, next) {
      if (next.status == AuthStatus.authenticated) {
        final role = next.user?.role ?? 'student';
        switch (role) {
          case 'teacher':
            context.go('/teacher');
            break;
          case 'parent':
            context.go('/parent');
            break;
          default:
            context.go('/student');
        }
      } else if (next.availableProfiles.isNotEmpty) {
        context.go('/auth/select-profile');
      }
    });

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              theme.colorScheme.primary,
              theme.colorScheme.primary.withValues(alpha: 0.8),
              theme.scaffoldBackgroundColor,
              theme.scaffoldBackgroundColor,
            ],
            stops: const [0.0, 0.25, 0.25, 1.0],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(height: 40),

                  // ── School Logo ──
                  ScaleTransition(
                    scale: _logoScale,
                    child: Container(
                      width: 100,
                      height: 100,
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(24),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.15),
                            blurRadius: 20,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(24),
                        child: branding.when(
                          data: (b) => b.logoUrl.isNotEmpty
                              ? CachedNetworkImage(
                                  imageUrl:
                                      '${AppConfig.apiBaseUrl}${b.logoUrl}',
                                  fit: BoxFit.cover,
                                  placeholder: (_, __) => Icon(
                                    Icons.school_rounded,
                                    size: 48,
                                    color: theme.colorScheme.primary,
                                  ),
                                  errorWidget: (_, __, ___) => Icon(
                                    Icons.school_rounded,
                                    size: 48,
                                    color: theme.colorScheme.primary,
                                  ),
                                )
                              : Icon(
                                  Icons.school_rounded,
                                  size: 48,
                                  color: theme.colorScheme.primary,
                                ),
                          loading: () => Icon(
                            Icons.school_rounded,
                            size: 48,
                            color: theme.colorScheme.primary,
                          ),
                          error: (_, __) => Icon(
                            Icons.school_rounded,
                            size: 48,
                            color: theme.colorScheme.primary,
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ── School Name ──
                  FadeInWidget(
                    delay: const Duration(milliseconds: 200),
                    child: Text(
                      branding.valueOrNull?.schoolName ?? AppConfig.schoolName,
                      style: const TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w700,
                        color: Colors.white,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                  if (branding.valueOrNull?.motto.isNotEmpty == true)
                    FadeInWidget(
                      delay: const Duration(milliseconds: 350),
                      child: Text(
                        branding.valueOrNull!.motto,
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.white.withValues(alpha: 0.85),
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  const SizedBox(height: 36),

                  // ── Login Form ──
                  SlideTransition(
                    position: Tween<Offset>(
                      begin: const Offset(0, 0.3),
                      end: Offset.zero,
                    ).animate(CurvedAnimation(
                      parent: _formAnimCtrl,
                      curve: Curves.easeOutCubic,
                    )),
                    child: FadeTransition(
                      opacity: _formAnimCtrl,
                      child: Container(
                        padding: const EdgeInsets.all(24),
                        decoration: BoxDecoration(
                          color: Colors.white,
                          borderRadius: BorderRadius.circular(24),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.08),
                              blurRadius: 24,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: Form(
                          key: _formKey,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              Text(
                                'Welcome Back',
                                style: TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w700,
                                  color: theme.textTheme.bodyLarge?.color,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Sign in with your school ID',
                                style: TextStyle(
                                  fontSize: 13,
                                  color: theme.textTheme.bodySmall?.color,
                                ),
                              ),
                              const SizedBox(height: 24),

                              // ── Login ID Field ──
                              TextFormField(
                                controller: _loginIdCtrl,
                                decoration: InputDecoration(
                                  prefixIcon: Icon(
                                    Icons.person_outline_rounded,
                                    color: theme.colorScheme.primary,
                                  ),
                                  hintText: 'Registration # / Phone / Email',
                                  labelText: 'Login ID',
                                ),
                                keyboardType: TextInputType.text,
                                textInputAction: TextInputAction.next,
                                validator: (v) =>
                                    v == null || v.trim().isEmpty
                                        ? 'Please enter your Login ID'
                                        : null,
                              ),
                              const SizedBox(height: 16),

                              // ── Password Field ──
                              TextFormField(
                                controller: _passwordCtrl,
                                obscureText: _obscurePassword,
                                decoration: InputDecoration(
                                  prefixIcon: Icon(
                                    Icons.lock_outline_rounded,
                                    color: theme.colorScheme.primary,
                                  ),
                                  hintText: 'Enter your password',
                                  labelText: 'Password',
                                  suffixIcon: IconButton(
                                    icon: Icon(
                                      _obscurePassword
                                          ? Icons.visibility_off_outlined
                                          : Icons.visibility_outlined,
                                      color: Colors.grey,
                                    ),
                                    onPressed: () => setState(
                                        () => _obscurePassword = !_obscurePassword),
                                  ),
                                ),
                                textInputAction: TextInputAction.done,
                                onFieldSubmitted: (_) => _handleLogin(),
                                validator: (v) =>
                                    v == null || v.isEmpty
                                        ? 'Please enter your password'
                                        : null,
                              ),
                              const SizedBox(height: 12),

                              // ── Remember Me + Forgot ──
                              Row(
                                children: [
                                  SizedBox(
                                    width: 22,
                                    height: 22,
                                    child: Checkbox(
                                      value: _rememberMe,
                                      onChanged: (v) =>
                                          setState(() => _rememberMe = v!),
                                      activeColor: theme.colorScheme.primary,
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(4),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  const Text(
                                    'Remember me',
                                    style: TextStyle(fontSize: 13),
                                  ),
                                  const Spacer(),
                                  GestureDetector(
                                    onTap: () {
                                      // TODO: Forgot password flow
                                    },
                                    child: Text(
                                      'Forgot Password?',
                                      style: TextStyle(
                                        fontSize: 13,
                                        fontWeight: FontWeight.w500,
                                        color: theme.colorScheme.primary,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 24),

                              // ── Error Message ──
                              if (authState.status == AuthStatus.error)
                                Container(
                                  padding: const EdgeInsets.all(12),
                                  margin: const EdgeInsets.only(bottom: 16),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFFEF2F2),
                                    borderRadius: BorderRadius.circular(10),
                                    border: Border.all(
                                        color: const Color(0xFFFECACA)),
                                  ),
                                  child: Row(
                                    children: [
                                      const Icon(Icons.error_outline,
                                          color: Color(0xFFEF4444), size: 18),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        child: Text(
                                          authState.errorMessage ??
                                              'Login failed',
                                          style: const TextStyle(
                                            fontSize: 13,
                                            color: Color(0xFFDC2626),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),

                              // ── Login Button ──
                              SizedBox(
                                height: 52,
                                child: ElevatedButton(
                                  onPressed:
                                      authState.status == AuthStatus.loading
                                          ? null
                                          : _handleLogin,
                                  style: ElevatedButton.styleFrom(
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(14),
                                    ),
                                  ),
                                  child: authState.status == AuthStatus.loading
                                      ? const SizedBox(
                                          width: 22,
                                          height: 22,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2.5,
                                            color: Colors.white,
                                          ),
                                        )
                                      : const Text(
                                          'Sign In',
                                          style: TextStyle(
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                          ),
                                        ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),

                  // ── Footer ──
                  FadeInWidget(
                    delay: const Duration(milliseconds: 600),
                    child: Text(
                      'Powered by VedaSchoolPro',
                      style: TextStyle(
                        fontSize: 12,
                        color: theme.textTheme.bodySmall?.color,
                      ),
                    ),
                  ),
                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
