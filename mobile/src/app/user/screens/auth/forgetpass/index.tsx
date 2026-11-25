import { View, Text, StyleSheet } from 'react-native';

export default function UserForgetPasswordScreen() {
  return (
    <View style={styles.container}>
      <Text>User Forget Password Screen</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
