import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/auth_provider.dart';
import '../../widgets/animated_card.dart';

/// Profile selection screen for users with multiple roles.
class ProfileSelectScreen extends ConsumerWidget {
  const ProfileSelectScreen({super.key});

  IconData _roleIcon(String role) {
    switch (role) {
      case 'teacher':
      case 'hod':
        return Icons.school_outlined;
      case 'parent':
        return Icons.family_restroom_outlined;
      case 'school_admin':
        return Icons.admin_panel_settings_outlined;
      case 'principal':
        return Icons.account_balance_outlined;
      case 'vice_principal':
        return Icons.supervised_user_circle_outlined;
      case 'chairman':
      case 'trust_member':
        return Icons.business_outlined;
      case 'staff':
      case 'accountant':
      case 'clerk':
      case 'librarian':
      case 'lab_assistant':
      case 'peon':
      case 'driver':
      case 'security':
      case 'non_teaching':
        return Icons.badge_outlined;
      default:
        return Icons.person_outline_rounded;
    }
  }

  String _roleLabel(String role) {
    switch (role) {
      case 'teacher':
        return 'Teacher';
      case 'hod':
        return 'Head of Department';
      case 'parent':
        return 'Parent';
      case 'school_admin':
        return 'School Admin';
      case 'principal':
        return 'Principal';
      case 'vice_principal':
        return 'Vice Principal';
      case 'chairman':
        return 'Chairman';
      case 'trust_member':
        return 'Trust Member';
      case 'accountant':
        return 'Accountant';
      case 'clerk':
        return 'Clerk';
      case 'librarian':
        return 'Librarian';
      case 'lab_assistant':
        return 'Lab Assistant';
      case 'driver':
        return 'Transport Staff';
      case 'security':
        return 'Security';
      case 'staff':
      case 'non_teaching':
      case 'peon':
        return 'Staff';
      default:
        return 'Student';
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);
    final theme = Theme.of(context);

    ref.listen(authProvider, (prev, next) {
      if (next.status == AuthStatus.authenticated) {
        final role = next.user?.role ?? 'student';
        switch (role) {
          case 'teacher':
            context.go('/teacher');
          case 'parent':
            context.go('/parent');
          default:
            context.go('/student');
        }
      }
    });

    return Scaffold(
      appBar: AppBar(
        title: const Text('Select Profile'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () {
            ref.read(authProvider.notifier).logout();
            context.go('/auth/login');
          },
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Choose your role',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text(
              'You have multiple profiles. Select one to continue.',
              style: TextStyle(
                fontSize: 14,
                color: theme.textTheme.bodySmall?.color,
              ),
            ),
            const SizedBox(height: 32),
            Expanded(
              child: ListView.builder(
                itemCount: authState.availableProfiles.length,
                itemBuilder: (ctx, i) {
                  final profile = authState.availableProfiles[i];
                  return AnimatedCard(
                    index: i,
                    onTap: () {
                      HapticFeedback.mediumImpact();
                      ref.read(authProvider.notifier).selectProfile(profile.id);
                    },
                    padding: const EdgeInsets.all(20),
                    child: Row(
                      children: [
                        Container(
                          width: 56,
                          height: 56,
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary
                                .withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Icon(
                            _roleIcon(profile.role),
                            color: theme.colorScheme.primary,
                            size: 28,
                          ),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                profile.label,
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                _roleLabel(profile.role),
                                style: TextStyle(
                                  fontSize: 13,
                                  color: theme.colorScheme.primary,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Icon(
                          Icons.arrow_forward_ios_rounded,
                          size: 16,
                          color: theme.textTheme.bodySmall?.color,
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            if (authState.status == AuthStatus.loading)
              const Center(child: CircularProgressIndicator()),
          ],
        ),
      ),
    );
  }
}
