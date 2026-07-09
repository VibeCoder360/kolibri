import { createTranslator } from 'kolibri/utils/i18n';

export const faceLoginStrings = createTranslator('FaceLoginStrings', {
  // Sign-in page
  documentTitle: {
    message: 'Sign in to Kolibri',
    context: 'Browser tab title for the face sign-in page.',
  },
  faceSignInTitle: {
    message: 'Sign in with your face',
    context: 'Title on the face sign-in page.',
  },
  faceSignInDescription: {
    message: 'Look at the camera to sign in',
    context: 'Instructions shown beneath the title on the face sign-in page.',
  },
  lookAtCamera: {
    message: 'Look straight at the camera',
    context: 'Instruction overlaid on the camera view during face sign-in.',
  },
  recognizing: {
    message: 'Recognizing…',
    context: 'Status shown while a captured face is being checked against enrolled users.',
  },
  loadingModels: {
    message: 'Preparing camera…',
    context: 'Status shown while the face recognition engine is loading.',
  },
  notRecognized: {
    message: "We couldn't recognize you. Try again or sign in another way.",
    context: 'Error shown when a face does not match any enrolled user.',
  },
  // Auth link / toggle
  signInWithFace: {
    message: 'Sign in with your face',
    context: 'Link text on the sign-in pages to switch to the face sign-in page.',
  },
  // Facility config
  enableFaceLogin: {
    message: 'Allow users to sign in with face recognition',
    context: "Option on 'Facility settings' page.",
  },
  enableFaceLoginDescription: {
    message:
      'Face data is stored only on this device and is never synced or sent to the internet. Make sure you have consent (from a parent or guardian for minors) before enrolling anyone.',
    context: 'Helper text under the face login option on the facility settings page.',
  },
  // Enrollment wizard
  setUpFaceSignIn: {
    message: 'Set up face sign-in',
    context: 'Button label that opens the face enrollment wizard.',
  },
  removeFaceSignIn: {
    message: 'Remove face sign-in',
    context: "Button label that deletes a user's face enrollment.",
  },
  removeConfirmation: {
    message:
      "This will delete this person's stored face data. They will no longer be able to sign in with their face until they enroll again.",
    context: 'Confirmation text shown before removing a face enrollment.',
  },
  faceEnrollmentInstructions: {
    message:
      'Take {total} pictures of your face: looking straight ahead, slightly left, and slightly right. Only a mathematical summary is stored — never a photo.',
    context: 'Instructions at the top of the face enrollment wizard.',
  },
  captureSample: {
    message: 'Capture',
    context: 'Button label that captures one face sample in the enrollment wizard.',
  },
  captureProgress: {
    message: 'Captured {count} of {total}',
    context: 'Progress indicator in the face enrollment wizard.',
  },
  captureFailedNoFace: {
    message: 'No face detected. Make sure your face is visible and well lit.',
    context: 'Error when a capture attempt finds no face in the frame.',
  },
  captureFailedMultipleFaces: {
    message: 'More than one face detected. Make sure only one person is in view.',
    context: 'Error when a capture attempt finds several faces in the frame.',
  },
  captureFailedLowQuality: {
    message: 'The picture was not clear enough. Move closer to the camera and try again.',
    context: 'Error when a capture attempt fails the quality checks.',
  },
  consentLabel: {
    message:
      "I confirm consent has been given to store this person's face data on this device",
    context:
      'Consent checkbox in the face enrollment wizard. Must be checked before saving.',
  },
  enrollmentSaved: {
    message: 'Face sign-in is set up',
    context: 'Success message after face enrollment is saved.',
  },
  enrollmentRemoved: {
    message: 'Face sign-in was removed',
    context: 'Success message after face enrollment is deleted.',
  },
  enrollmentFailed: {
    message: 'Could not save face sign-in. Please try again.',
    context: 'Error shown when saving or removing face enrollment fails.',
  },
  startOver: {
    message: 'Start over',
    context: 'Button label that discards captured samples and restarts the wizard.',
  },
});
