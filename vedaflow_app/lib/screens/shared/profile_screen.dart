import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:cached_network_image/cached_network_image.dart';
import '../../core/config.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/animated_card.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // ── Profile Header ──
            AnimatedCard(
              index: 0,
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  // Photo
                  Container(
                    width: 88,
                    height: 88,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: theme.colorScheme.primary.withValues(alpha: 0.2),
                        width: 3,
                      ),
                    ),
                    child: CircleAvatar(
                      radius: 40,
                      backgroundColor:
                          theme.colorScheme.primary.withValues(alpha: 0.1),
                      child: user?.photoUrl != null
                          ? ClipOval(
                              child: CachedNetworkImage(
                                imageUrl:
                                    '${AppConfig.apiBaseUrl}${user!.photoUrl}',
                                width: 80,
                                height: 80,
                                fit: BoxFit.cover,
                              ),
                            )
                          : Text(
                              (user?.name ?? 'U').substring(0, 1).toUpperCase(),
                              style: TextStyle(
                                color: theme.colorScheme.primary,
                                fontSize: 32,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    user?.name ?? 'User',
                    style: const TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      (user?.role ?? 'student').toUpperCase(),
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                  if (user?.email != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      user!.email,
                      style: TextStyle(
                        fontSize: 13,
                        color: theme.textTheme.bodySmall?.color,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 16),

            // ── Info Items ──
            if (user?.className != null)
              _infoTile(context, Icons.class_outlined, 'Class',
                  '${user!.className} ${user.sectionName ?? ''}', 1),
            if (user?.registrationNumber != null)
              _infoTile(context, Icons.badge_outlined, 'Registration #',
                  user!.registrationNumber!, 2),

            const SizedBox(height: 16),

            // ── Actions ──
            AnimatedCard(
              index: 5,
              padding: EdgeInsets.zero,
              child: Column(
                children: [
                  _actionTile(
                    context,
                    Icons.lock_outline_rounded,
                    'Change Password',
                    () {
                      // TODO: Change password screen
                    },
                  ),
                  const Divider(height: 1, indent: 56),
                  _actionTile(
                    context,
                    Icons.language_rounded,
                    'Language',
                    () {
                      // TODO: Language picker
                    },
                  ),
                  const Divider(height: 1, indent: 56),
                  _actionTile(
                    context,
                    Icons.info_outline_rounded,
                    'About',
                    () {
                      showAboutDialog(
                        context: context,
                        applicationName: 'VedaSchoolPro',
                        applicationVersion: '1.0.0',
                        children: [
                          const Text('Smart School Management System'),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // ── Logout ──
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {
                  showDialog(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('Logout'),
                      content:
                          const Text('Are you sure you want to sign out?'),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(ctx),
                          child: const Text('Cancel'),
                        ),
                        ElevatedButton(
                          onPressed: () {
                            Navigator.pop(ctx);
                            HapticFeedback.mediumImpact();
                            ref.read(authProvider.notifier).logout();
                            context.go('/auth/login');
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFFEF4444),
                          ),
                          child: const Text('Logout'),
                        ),
                      ],
                    ),
                  );
                },
                icon: const Icon(Icons.logout_rounded, color: Color(0xFFEF4444)),
                label: const Text(
                  'Sign Out',
                  style: TextStyle(color: Color(0xFFEF4444)),
                ),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Color(0xFFEF4444)),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  Widget _infoTile(
      BuildContext context, IconData icon, String label, String value, int i) {
    final theme = Theme.of(context);
    return AnimatedCard(
      index: i,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Icon(icon, color: theme.colorScheme.primary, size: 22),
          const SizedBox(width: 14),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  color: theme.textTheme.bodySmall?.color,
                ),
              ),
              Text(
                value,
                style: const TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _actionTile(
      BuildContext context, IconData icon, String label, VoidCallback onTap) {
    return ListTile(
      leading: Icon(icon, color: Theme.of(context).colorScheme.primary),
      title: Text(label, style: const TextStyle(fontSize: 14)),
      trailing: const Icon(Icons.chevron_right_rounded, size: 20),
      onTap: onTap,
    );
  }
}
